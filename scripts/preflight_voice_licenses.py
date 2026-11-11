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


def license_from_card(text):
    match = re.search(r"(?im)^\s*license\s*:\s*([^\r\n#]+)", text)
    return match.group(1).strip().strip("'\"") if match else None


def fetch_license_file(revision, path):
    quoted = urllib.parse.quote(path, safe="/")
    url = f"https://huggingface.co/rhasspy/piper-voices/resolve/{revision}/{quoted}?download=true"
    try:
        data, final_url, header_revision = fetch_text(url)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return {"path": path, "status": "not_present_at_pinned_revision"}
        raise
    return {
        "path": path,
        "status": "read",
        "url": url,
        "resolved_url": final_url,
        "header_revision": header_revision,
        "bytes": len(data),
        "sha256": sha256(data),
        "text": data.decode("utf-8", errors="replace"),
    }


def preflight(lock_path):
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    revisions = {model["revision"] for model in lock["models"]}
    if len(revisions) != 1:
        raise ValueError("All bundled voice models must use the same locked revision")
    revision = revisions.pop()
    encoded_revision = urllib.parse.quote(revision, safe="")
    api_url = f"https://huggingface.co/api/models/rhasspy/piper-voices?revision={encoded_revision}"
    api_bytes, api_resolved_url, _ = fetch_text(api_url)
    metadata = json.loads(api_bytes)
    api_revision = metadata.get("sha")
    if api_revision != revision:
        raise ValueError(f"HF API revision mismatch: expected={revision} returned={api_revision!r}")

    card_data = metadata.get("cardData") or {}
    model_records = []
    for model in lock["models"]:
        card_item = next((item for item in model["files"] if item["name"].endswith("MODEL_CARD.txt")), None)
        if card_item is None:
            raise ValueError(f"No pinned model card in lock for {model['accent']}")
        card_bytes, card_url, header_revision = fetch_text(card_item["url"])
        if len(card_bytes) != card_item["bytes"] or sha256(card_bytes) != card_item["sha256"]:
            raise ValueError(f"Pinned model-card size/SHA mismatch for {model['accent']}")
        card_text = card_bytes.decode("utf-8", errors="replace")
        model_records.append(
            {
                "accent": model["accent"],
                "revision": model["revision"],
                "model_card_url": card_item["url"],
                "resolved_url": card_url,
                "header_revision": header_revision,
                "bytes": len(card_bytes),
                "sha256": sha256(card_bytes),
                "card_license": license_from_card(card_text),
                "card_text": card_text,
            }
        )

    root_files = metadata.get("siblings") or []
    root_license_paths = sorted(
        item.get("rfilename", "")
        for item in root_files
        if "/" not in item.get("rfilename", "")
        and re.match(r"^(LICENSE|COPYING|NOTICE)(\.|$)", item.get("rfilename", ""), re.I)
    )
    license_files = [fetch_license_file(revision, path) for path in root_license_paths]

    return {
        "revision_requested": revision,
        "revision_returned": api_revision,
        "api_url": api_url,
        "api_resolved_url": api_resolved_url,
        "repo_id": metadata.get("id"),
        "repo_license_metadata": card_data.get("license") or metadata.get("license"),
        "repo_license_metadata_fields": {key: value for key, value in card_data.items() if "license" in key.lower()},
        "license_files": license_files,
        "models": model_records,
        "weights_fetched": False,
        "redistribution_decision": "metadata evidence only; human/high-model review remains required",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = preflight(args.lock)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"revision": result["revision_returned"], "repo_license": result["repo_license_metadata"], "models": [{"accent": item["accent"], "sha256": item["sha256"], "license": item["card_license"]} for item in result["models"]], "weights_fetched": False}, sort_keys=True))


if __name__ == "__main__":
    main()
