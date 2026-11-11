"""Candidate path and payload checks for the preinstalled Windows voice pack."""
import hashlib
import json
import os
from pathlib import Path

from voice_profile import voice_files


def _valid_voice(folder, accent):
    try:
        voice_files(folder, accent)
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def choose_voice_folder(user_root, resource_root, accent):
    """Prefer a complete user voice per accent; otherwise use the bundled pair."""
    user_folder = Path(user_root) / "voices" / ("uk" if accent == 1 else "us")
    bundled_folder = Path(resource_root) / "speech" / "voices" / ("uk" if accent == 1 else "us")
    if _valid_voice(user_folder, accent):
        return user_folder
    if _valid_voice(bundled_folder, accent):
        return bundled_folder
    return user_folder


def choose_runtime_dir(user_root, resource_root):
    """Resolve the engine independently from model directories."""
    candidates = (
        Path(user_root) / "runtime" / "piper",
        Path(user_root) / "runtime",
        Path(resource_root) / "speech" / "runtime" / "piper",
        Path(resource_root) / "speech" / "runtime",
    )
    for directory in candidates:
        if (directory / "piper.exe").is_file():
            return directory
    return candidates[0]


def cache_output_path(cache_root, word_key):
    """Create a unique writable cache temp path; never write beside installed EXEs."""
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(word_key.encode("utf-8")).hexdigest()
    return cache_root / (digest + ".part.wav")


def audit_bundle(root, model_lock, runtime_manifest):
    """Accept exact model files and recorded runtime files; reject every other payload."""
    root = Path(root)
    expected = {}
    for model in model_lock["models"]:
        accent = model["accent"]
        for item in model["files"]:
            rel = Path("speech") / "voices" / accent / item["name"]
            expected[rel.as_posix()] = (item["bytes"], item["sha256"])
    for item in runtime_manifest["files"]:
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() in expected:
            raise ValueError(f"Invalid runtime path: {item['path']}")
        expected[rel.as_posix()] = (item["bytes"], item["sha256"])
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise ValueError(f"Bundle tree mismatch; missing={missing}; extra={extra}")
    verified = []
    for rel, (size, expected_hash) in expected.items():
        path = actual[rel]
        if path.stat().st_size != size:
            raise ValueError(f"Byte count mismatch: {rel}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected_hash:
            raise ValueError(f"SHA-256 mismatch: {rel}")
        verified.append(rel)
    return {"files": len(verified), "paths": sorted(verified)}
