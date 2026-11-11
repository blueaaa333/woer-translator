"""Read fixed-revision model metadata/cards only; never fetch voice weights."""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


USER_AGENT = "WoerTranslator-voice-license-preflight/1"
MAX_TEXT_BYTES = 256 * 1024
SPDX_MIT_URL = "https://raw.githubusercontent.com/spdx/license-list-data/v3.26.0/text/MIT.txt"
SPDX_MIT_GIT_BLOB_SHA1 = "fc2cf8e6b667b752cf62d1306521071db34c0a63"


def fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_TEXT_BYTES + 1)
            if len(data) > MAX_TEXT_BYTES:
                raise ValueError(f"Text response exceeds {MAX_TEXT_BYTES} bytes: {url}")
            return data, response.geturl(), response.headers.get("X-Repo-Commit")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} reading fixed-revision metadata: {url}") from exc


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def license_from_card(text):
    match = re.search(r"(?im)^\s*license\s*:\s*([^\r\n#]+)", text)
    return match.group(1).strip().strip("'\"") if match else None


def copyright_lines(text):
    return [line.strip() for line in text.splitlines() if re.search(r"(?i)(copyright|©)", line)]


def fetch_revision_file(revision, path):
    quoted = urllib.parse.quote(path, safe="/")
    url = f"https://huggingface.co/rhasspy/piper-voices/resolve/{revision}/{quoted}?download=true"
    try:
        data, final_url, header_revision = fetch_text(url)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return {"path": path, "status": "not_present_at_pinned_revision"}
        raise
    if header_revision and header_revision != revision:
        raise ValueError(f"HF file revision mismatch for {path}: expected={revision} returned={header_revision}")
    text = data.decode("utf-8", errors="replace")
    return {
        "path": path,
        "status": "read",
        "url": url,
        "resolved_url": final_url,
        "header_revision": header_revision,
        "bytes": len(data),
        "sha256": sha256(data),
        "license_metadata": license_from_card(text),
        "text": text,
    }


def preflight(lock_path):
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    revisions = {model["revision"] for model in lock["models"]}
    if len(revisions) != 1:
        raise ValueError("All bundled voice models must use the same locked revision")
    revision = revisions.pop()
    api_url = f"https://huggingface.co/api/models/rhasspy/piper-voices/tree/{revision}?recursive=false"
    api_bytes, api_resolved_url, api_header_revision = fetch_text(api_url)
    tree = json.loads(api_bytes)
    if not isinstance(tree, list):
        raise ValueError("HF fixed-revision tree response was not a list")
    if api_header_revision and api_header_revision != revision:
        raise ValueError(f"HF tree revision mismatch: expected={revision} returned={api_header_revision!r}")
    root_paths = {item.get("path") for item in tree if item.get("type") == "file"}

    model_records = []
    for model in lock["models"]:
        card_item = next((item for item in model["files"] if item["name"].endswith("MODEL_CARD.txt")), None)
        if card_item is None:
            raise ValueError(f"No pinned model card in lock for {model['accent']}")
        card_url_path = urllib.parse.urlsplit(card_item["url"]).path
        prefix = f"/rhasspy/piper-voices/resolve/{model['revision']}/"
        if not card_url_path.startswith(prefix):
            raise ValueError(f"Model-card URL is not pinned to its lock revision: {card_item['url']}")
        card_path = urllib.parse.unquote(card_url_path[len(prefix):])
        card = fetch_revision_file(model["revision"], card_path)
        if card.get("status") != "read":
            raise ValueError(f"Pinned model card is unavailable for {model['accent']}")
        if card["bytes"] != card_item["bytes"] or card["sha256"] != card_item["sha256"]:
            raise ValueError(f"Pinned model-card size/SHA mismatch for {model['accent']}")
        card_text = card["text"]
        model_records.append(
            {
                "accent": model["accent"],
                "revision": model["revision"],
                "model_card_url": card_item["url"],
                "resolved_url": card["resolved_url"],
                "header_revision": card["header_revision"],
                "bytes": card["bytes"],
                "sha256": card["sha256"],
                "card_license": license_from_card(card_text),
                "card_text": card_text,
            }
        )

    root_license_paths = sorted(
        path for path in root_paths
        if path and re.match(r"^(LICENSE|COPYING|NOTICE)(\.|$)", path, re.I)
    )
    license_files = [fetch_revision_file(revision, path) for path in root_license_paths]
    readme = fetch_revision_file(revision, "README.md") if "README.md" in root_paths else None
    mit_bytes, mit_resolved_url, _ = fetch_text(SPDX_MIT_URL)
    actual_mit_blob = git_blob_sha1(mit_bytes)
    if actual_mit_blob != SPDX_MIT_GIT_BLOB_SHA1:
        raise ValueError(f"SPDX MIT text changed: expected git blob {SPDX_MIT_GIT_BLOB_SHA1}, got {actual_mit_blob}")
    mit_text = mit_bytes.decode("utf-8")
    if not readme or readme.get("license_metadata", "").lower() != "mit":
        raise ValueError("Fixed-revision HF root README does not declare MIT")
    if readme.get("header_revision") and readme["header_revision"] != revision:
        raise ValueError("Fixed-revision HF README revision header does not match the lock")
    notice_sources = []
    if readme:
        notice_sources.append({"source": "README.md", "sha256": readme["sha256"], "lines": copyright_lines(readme["text"])})
    for item in license_files:
        if item.get("status") == "read":
            notice_sources.append({"source": item["path"], "sha256": item["sha256"], "lines": copyright_lines(item["text"])})
    for item in model_records:
        notice_sources.append({"source": item["model_card_url"], "sha256": item["sha256"], "lines": copyright_lines(item["card_text"])})

    return {
        "revision_requested": revision,
        "revision_returned": api_header_revision or revision,
        "api_url": api_url,
        "api_resolved_url": api_resolved_url,
        "repo_license_metadata": readme["license_metadata"] if readme else None,
        "repo_license_text": readme,
        "license_files": license_files,
        "copyright_notice_sources": notice_sources,
        "copyright_notice_finding": "No explicit copyright notice found in the pinned README, root license files, or selected model cards; no copyright holder or year is inferred." if not any(item["lines"] for item in notice_sources) else "Only the exact notice lines listed in copyright_notice_sources are recorded; no holder/year is inferred.",
        "standard_mit_terms": {
            "url": SPDX_MIT_URL,
            "resolved_url": mit_resolved_url,
            "git_blob_sha1": actual_mit_blob,
            "sha256": sha256(mit_bytes),
            "text": mit_text,
            "notice": "The template retains <year> and <copyright holders>; no owner or year is inferred. No root LICENSE/COPYING/NOTICE file was listed at the pinned HF revision." if not license_files else "The repository license files are preserved separately; no owner or year is inferred.",
        },
        "models": model_records,
        "weights_fetched": False,
        "redistribution_decision": "Astra approved the fixed-revision MIT/model-card evidence for this CI test only; this is not formal release approval.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = preflight(args.lock)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme = result["repo_license_text"]
    print(json.dumps({
        "requested_revision": result["revision_requested"],
        "resolved_revision": result["revision_returned"],
        "repo_license": result["repo_license_metadata"],
        "repo_readme": {
            "url": readme["url"],
            "resolved_url": readme["resolved_url"],
            "header_revision": readme["header_revision"],
            "sha256": readme["sha256"],
            "excerpt": readme["text"][:1500],
        } if readme else None,
        "license_files": [{
            "path": item["path"],
            "status": item["status"],
            "bytes": item.get("bytes"),
            "sha256": item.get("sha256"),
            "excerpt": item.get("text", "")[:2500],
        } for item in result["license_files"]],
        "standard_mit_terms": {
            "url": result["standard_mit_terms"]["url"],
            "resolved_url": result["standard_mit_terms"]["resolved_url"],
            "git_blob_sha1": result["standard_mit_terms"]["git_blob_sha1"],
            "sha256": result["standard_mit_terms"]["sha256"],
            "text": result["standard_mit_terms"]["text"],
            "notice": result["standard_mit_terms"]["notice"],
        },
        "copyright_notice_sources": result["copyright_notice_sources"],
        "copyright_notice_finding": result["copyright_notice_finding"],
        "models": [{
            "accent": item["accent"],
            "resolved_url": item["resolved_url"],
            "header_revision": item["header_revision"],
            "sha256": item["sha256"],
            "license": item["card_license"],
            "card_text": item["card_text"],
        } for item in result["models"]],
        "weights_fetched": False,
        "redistribution_decision": result["redistribution_decision"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
