"""Build the public words.db from one pinned ECDICT CSV snapshot."""
import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "39cfb9672c0906b63569e0453c2e6abfb9ab182a"
SOURCE_SHA256 = "d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc"
SOURCE_BYTES = 66009548
SOURCE_URL = f"https://raw.githubusercontent.com/skywind3000/ECDICT/{UPSTREAM_COMMIT}/ecdict.csv"
SOURCE_HOST = "raw.githubusercontent.com"
FIELDS = ("word", "phonetic", "translation", "definition", "tag")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def fetch_source(destination):
    destination = Path(destination)
    if destination.exists():
        size = destination.stat().st_size
        digest = sha256_file(destination)
        if size == SOURCE_BYTES and digest == SOURCE_SHA256:
            return destination
        raise ValueError(f"Refusing unexpected cached ECDICT source: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="ecdict-", suffix=".part", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "WoerTranslator-open-data-builder"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            host = urllib.parse.urlsplit(response.geturl()).hostname
            if host != SOURCE_HOST:
                raise ValueError(f"Unexpected ECDICT redirect host: {host}")
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                size += len(block)
        if size != SOURCE_BYTES:
            raise ValueError(f"ECDICT source size mismatch: expected {SOURCE_BYTES}, got {size}")
        actual = digest.hexdigest()
        if actual != SOURCE_SHA256:
            raise ValueError(f"ECDICT source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual}")
        temporary.replace(destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def _merge_text(existing, incoming):
    if not existing:
        return incoming or ""
    if not incoming or incoming == existing:
        return existing
    return existing + "\n" + incoming


def build_database(source, output):
    source = Path(source)
    if source.stat().st_size != SOURCE_BYTES:
        raise ValueError(f"ECDICT source size mismatch: expected {SOURCE_BYTES}, got {source.stat().st_size}")
    source_hash = sha256_file(source)
    if source_hash != SOURCE_SHA256:
        raise ValueError(f"ECDICT source SHA-256 mismatch: expected {SOURCE_SHA256}, got {source_hash}")

    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing dictionary database: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".building")
    if temporary.exists():
        raise FileExistsError(f"Refusing to overwrite temporary database: {temporary}")

    rows = 0
    translated_rows = 0
    skipped_empty_word = 0
    connection = sqlite3.connect(temporary)
    connection.create_function("merge_text", 2, _merge_text, deterministic=True)
    try:
        connection.executescript(
            "CREATE TABLE words ("
            "word TEXT PRIMARY KEY, phonetic TEXT, translation TEXT, definition TEXT, tag TEXT);"
        )
        upsert = """INSERT INTO words(word,phonetic,translation,definition,tag)
VALUES(?,?,?,?,?) ON CONFLICT(word) DO UPDATE SET
phonetic=merge_text(words.phonetic,excluded.phonetic),
translation=merge_text(words.translation,excluded.translation),
definition=merge_text(words.definition,excluded.definition),
tag=merge_text(words.tag,excluded.tag)"""
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = set(FIELDS) - set(reader.fieldnames or ())
            if missing:
                raise ValueError("ECDICT CSV is missing required columns: " + ", ".join(sorted(missing)))
            with connection:
                for row in reader:
                    word = (row.get("word") or "").strip().lower()
                    if not word:
                        skipped_empty_word += 1
                        continue
                    values = tuple(row.get(field) or "" for field in FIELDS[1:])
                    connection.execute(upsert, (word, *values))
                    rows += 1
                    translated_rows += bool(values[1].strip())
        connection.execute("PRAGMA optimize")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Generated ECDICT database failed SQLite integrity_check")
        connection.commit()
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
    connection.close()
    database_hash = sha256_file(temporary)
    unique_words = sqlite3.connect(temporary)
    try:
        headwords = unique_words.execute("SELECT count(*) FROM words").fetchone()[0]
    finally:
        unique_words.close()
    temporary.replace(output)
    return {
        "source_commit": UPSTREAM_COMMIT,
        "source_sha256": source_hash,
        "source_rows": rows,
        "headwords": headwords,
        "translated_rows": translated_rows,
        "skipped_empty_word": skipped_empty_word,
        "database_sha256": database_hash,
        "database_path": str(output),
    }


def build_bundle(source, output, archive=None, manifest=None):
    output = Path(output)
    archive = Path(archive) if archive else output.with_suffix(".db.gz")
    manifest = Path(manifest) if manifest else output.parent / "manifest.json"
    if manifest.exists() and output.exists() and archive.exists():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            recorded.get("source_commit") == UPSTREAM_COMMIT
            and recorded.get("source_sha256") == SOURCE_SHA256
            and recorded.get("database_sha256") == sha256_file(output)
            and recorded.get("archive_sha256") == sha256_file(archive)
        ):
            return recorded
    if output.exists() or archive.exists() or manifest.exists():
        raise FileExistsError("Refusing to overwrite an unverified ECDICT build bundle")

    stats = build_database(source, output)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = archive.with_name(archive.name + ".building")
    if temporary_archive.exists():
        raise FileExistsError(f"Refusing to overwrite temporary archive: {temporary_archive}")
    try:
        with output.open("rb") as source_stream, temporary_archive.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                shutil.copyfileobj(source_stream, compressed, 1024 * 1024)
        stats.update(
            archive_path=str(archive),
            archive_bytes=temporary_archive.stat().st_size,
            archive_sha256=sha256_file(temporary_archive),
            database_bytes=output.stat().st_size,
        )
        temporary_archive.replace(archive)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return stats
    except Exception:
        if temporary_archive.exists():
            temporary_archive.unlink()
        if output.exists():
            output.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Use a local copy of the exact pinned CSV")
    parser.add_argument("--output", type=Path, required=True, help="New SQLite database path; existing files are refused")
    parser.add_argument("--archive", type=Path, help="Compressed database path (default: output path with .db.gz suffix)")
    parser.add_argument("--manifest", type=Path, help="Build manifest path (default: output directory/manifest.json)")
    args = parser.parse_args()
    source = args.source or args.output.parent / "ecdict.csv"
    if args.source is None:
        fetch_source(source)
    print(json.dumps(build_bundle(source, args.output, args.archive, args.manifest), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
