"""Fetch only the two pinned public voices; never fetch the legacy Piper ZIP."""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 4 * 1024 * 1024


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            hasher.update(block)
    return hasher.hexdigest()


def fetch_one(item, target, opener=urllib.request.urlopen):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size == item["bytes"] and digest(target) == item["sha256"]:
        return

    partial = target.with_suffix(target.suffix + ".part")
    try:
        if target.suffix == ".onnx":
            with partial.open("wb") as output:
                for start in range(0, item["bytes"], CHUNK):
                    end = min(start + CHUNK, item["bytes"]) - 1
                    for attempt in range(3):
                        separator = "&" if "?" in item["url"] else "?"
                        url = item["url"] + separator + urllib.parse.urlencode(
                            {"download": "true", "woer_segment": start, "attempt": attempt}
                        )
                        request = urllib.request.Request(
                            url,
                            headers={
                                "User-Agent": "WoerTranslator-voice-runtime-probe/1",
                                "Range": f"bytes={start}-{end}",
                                "Cache-Control": "no-cache",
                            },
                        )
                        try:
                            with opener(request, timeout=60) as response:
                                data = response.read(end - start + 2)
                                expected_range = f"bytes {start}-"
                                if (
                                    len(data) != end - start + 1
                                    or not response.headers.get("Content-Range", "").startswith(expected_range)
                                ):
                                    raise ValueError("Invalid ranged model response")
                            output.write(data)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
        else:
            request = urllib.request.Request(
                item["url"], headers={"User-Agent": "WoerTranslator-voice-runtime-probe/1"}
            )
            with opener(request, timeout=60) as response, partial.open("wb") as output:
                while block := response.read(CHUNK):
                    output.write(block)

        if partial.stat().st_size != item["bytes"]:
            raise ValueError(f"Byte count mismatch for {target.name}")
        actual = digest(partial)
        if actual != item["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {target.name}: {actual}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def fetch_models(lock_path, destination):
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    destination = Path(destination).resolve()
    manifest = {"profile": lock["profile"], "models": []}
    for model in lock["models"]:
        folder = destination / "speech" / "voices" / model["accent"]
        for item in model["files"]:
            fetch_one(item, folder / item["name"])
        manifest["models"].append(
            {
                "accent": model["accent"],
                "revision": model["revision"],
                "files": [
                    {"name": item["name"], "bytes": item["bytes"], "sha256": item["sha256"]}
                    for item in model["files"]
                ],
                "license_evidence": model["license_evidence"],
            }
        )
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "voice-model-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    fetch_models(args.lock, args.dest)
