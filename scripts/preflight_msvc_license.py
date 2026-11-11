"""Read official Microsoft redistribution terms and report text-only evidence."""
import argparse
import hashlib
import io
import json
import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


SOURCES = {
    "visual_studio_enterprise_2022": {
        "url": "https://visualstudio.microsoft.com/wp-content/uploads/2021/11/Visual-Studio-2022-Enterprise-Professional-License-EN.docx",
        "page": "https://visualstudio.microsoft.com/license-terms/vs2022-ga-proenterprise/",
        "published": "2021-11-01",
        "topics": ("distributable code", "redist.txt", "you may copy", "distribute"),
    },
    "visual_cpp_runtime_2015_2022": {
        "url": "https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx",
        "page": "https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/",
        "published": "2021-11-01",
        "topics": ("redistributable", "distributable code", "distribute", "license terms"),
    },
    "visual_studio_2022_redistribution_list": {
        "url": "https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution",
        "page": "https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution",
        "published": None,
        "topics": ("distributable list", "redist.txt", "visual c++ runtime files", "subject to the license terms"),
    },
}
ALLOWED_HOSTS = {"visualstudio.microsoft.com", "learn.microsoft.com"}
MAX_DOWNLOAD_BYTES = 2_000_000
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "WoerTranslator-license-preflight/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final_url = response.geturl()
        if urlparse(final_url).hostname not in ALLOWED_HOSTS:
            raise ValueError(f"Unexpected official-license redirect host: {final_url}")
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Official source exceeds the {MAX_DOWNLOAD_BYTES}-byte preflight limit: {url}")
    return data, final_url


def docx_paragraphs(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in document.iter(f"{{{WORD_NS}}}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{{{WORD_NS}}}t")).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self.active = []

    def handle_data(self, data):
        if self.active is not None:
            self.active.append(data)

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3", "p", "li"} and self.active is not None:
            text = re.sub(r"\s+", " ", " ".join(self.active)).strip()
            if text:
                self.blocks.append(text)
            self.active = None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def limited_excerpt(paragraphs):
    # Keep no more than 24 exact words from each Microsoft document in the report.
    candidates = [p for p in paragraphs if re.search(r"distribut|redist|license term", p, re.I)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: sum(term in p.casefold() for term in ("may", "unmodified", "redist", "license terms", "subject to")), reverse=True)
    words = candidates[0].split()
    return " ".join(words[:24])


def inspect_docx(name, spec, data, final_url):
    paragraphs = docx_paragraphs(data)
    matches = []
    for index, text in enumerate(paragraphs):
        lowered = text.casefold()
        topics = [topic for topic in spec["topics"] if topic in lowered]
        if topics:
            matches.append({
                "paragraph_index": index,
                "characters": len(text),
                "sha256": sha256(text.encode("utf-8")),
                "topics": topics,
                "flags": {
                    "mentions_unmodified": "unmodified" in lowered,
                    "mentions_redist_list": "redist.txt" in lowered or "redist list" in lowered,
                    "mentions_license_terms": "license term" in lowered,
                    "mentions_redistribution": "distribut" in lowered or "redistribut" in lowered,
                },
            })
    if not matches:
        raise ValueError(f"No redistribution-related paragraphs were found in {name}")
    return {
        "source_url": spec["url"],
        "license_page": spec["page"],
        "published_date_from_page": spec["published"],
        "resolved_url": final_url,
        "bytes": len(data),
        "sha256": sha256(data),
        "paragraph_count": len(paragraphs),
        "relevant_paragraphs": matches[:12],
        "short_excerpt_max_24_words": limited_excerpt(paragraphs),
    }


def run():
    evidence = {"captured_utc": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name in ("visual_studio_enterprise_2022", "visual_cpp_runtime_2015_2022"):
        spec = SOURCES[name]
        data, final_url = fetch(spec["url"])
        evidence["sources"][name] = inspect_docx(name, spec, data, final_url)

    spec = SOURCES["visual_studio_2022_redistribution_list"]
    data, final_url = fetch(spec["url"])
    parser = PageText()
    parser.feed(data.decode("utf-8", errors="replace"))
    matching = []
    for index, text in enumerate(parser.blocks):
        lowered = text.casefold()
        topics = [topic for topic in spec["topics"] if topic in lowered]
        if topics:
            matching.append({
                "block_index": index,
                "characters": len(text),
                "sha256": sha256(text.encode("utf-8")),
                "topics": topics,
                "_text": text,
            })
    if not matching:
        raise ValueError("No REDIST or Visual C++ redistribution passages were found on Microsoft's official page")
    evidence["sources"]["visual_studio_2022_redistribution_list"] = {
        "source_url": spec["url"],
        "resolved_url": final_url,
        "captured_utc": evidence["captured_utc"],
        "bytes": len(data),
        "sha256": sha256(data),
        "relevant_blocks": [{key: value for key, value in block.items() if key != "_text"} for block in matching[:12]],
        "short_excerpt_max_24_words": " ".join(matching[0]["_text"].split()[:24]),
    }
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    evidence = run()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

