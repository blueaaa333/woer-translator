"""Exercise the application's SpeechEngine against a staged read-only bundle."""
import argparse
import getpass
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
def blocked_network(*_args, **_kwargs):
    raise AssertionError("A network call was attempted during the offline synthesis test")

from pronunciation import SpeechEngine
from voice_profile import voice_files


class OfflineRecordings:
    """Block the optional recording service while preserving the app preference."""
    folder = Path(".")
    last = None

    def cached(self, *_args):
        return None

    def get(self, *_args):
        raise AssertionError("Network recording access was attempted during offline smoke")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_pinned_tree(root, lock, runtime_manifest):
    expected = {}
    for model in lock["models"]:
        for item in model["files"]:
            relative = Path("speech") / "voices" / model["accent"] / item["name"]
            expected[relative.as_posix()] = (item["bytes"], item["sha256"])
    for item in runtime_manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid runtime manifest path: {item['path']}")
        expected[relative.as_posix()] = (item["bytes"], item["sha256"])
    actual = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    if set(actual) != set(expected):
        raise ValueError(f"Staged package tree mismatch: missing={sorted(set(expected)-set(actual))}; extra={sorted(set(actual)-set(expected))}")
    for name, (size, expected_hash) in expected.items():
        path = actual[name]
        if path.stat().st_size != size or file_sha256(path) != expected_hash:
            raise ValueError(f"Staged package hash mismatch: {name}")
    return sorted(expected)


def make_read_only(root):
    user = os.environ.get("USERNAME") or getpass.getuser()
    try:
        subprocess.run(
            ["icacls", str(root), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)(RX)",
             "/deny", f"{user}:(OI)(CI)(AD,WD,DC,DE)", "/T", "/C"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
    except Exception:
        restore_writable(root)
        raise
    probe = root / "write-probe.tmp"
    try:
        probe.write_text("must fail", encoding="ascii")
    except OSError:
        pass
    else:
        probe.unlink(missing_ok=True)
        restore_writable(root)
        raise AssertionError("Staged install tree is still writable")
    try:
        existing = next(path for path in root.rglob("*") if path.is_file())
    except Exception:
        restore_writable(root)
        raise
    try:
        with existing.open("r+b") as stream:
            original = stream.read(1)
            stream.seek(0)
            stream.write(original)
    except OSError:
        return
    else:
        restore_writable(root)
        raise AssertionError("An installed file is still writable")


def restore_writable(root):
    user = os.environ.get("USERNAME") or getpass.getuser()
    subprocess.run(
        ["icacls", str(root), "/remove:d", user, "/T", "/C"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["icacls", str(root), "/inheritance:e", "/grant:r", f"{user}:(OI)(CI)(F)", "/T", "/C"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def audio_summary(path, accent):
    with wave.open(str(path), "rb") as audio:
        params = audio.getparams()
        pcm = audio.readframes(audio.getnframes())
    if params.sampwidth != 2 or params.nframes <= 0 or len(pcm) == 0 or not any(pcm):
        raise ValueError(f"Invalid or silent {accent} PCM")
    if params.nframes <= params.framerate * 0.1:
        raise ValueError(f"{accent} PCM duration is too short")
    return {
        "accent": accent,
        "sample_rate": params.framerate,
        "channels": params.nchannels,
        "frames": params.nframes,
        "pcm_bytes": len(pcm),
        "sha256": file_sha256(path),
    }


def run_smoke(args):
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    runtime_manifest = json.loads((args.build_root / "runtime-manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="woer-voice-smoke-") as temp:
        scratch = Path(temp)
        package_root = scratch / "Woer Install 汉字 Space"
        user_data = scratch / "用户 数据 Space"
        speech_root = package_root / "speech"
        runtime_target = speech_root / "runtime" / "piper"
        voices_target = speech_root / "voices"
        runtime_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.runtime, runtime_target)
        shutil.copytree(args.models, voices_target)

        # Deliberately leave only the model in UK and only the config in US.
        # The runtime must resolve each complete bundled pair independently.
        user_root = user_data / "speech"
        (user_root / "voices" / "uk").mkdir(parents=True)
        (user_root / "voices" / "uk" / "dictionary-voice.onnx").write_bytes(b"truncated model")
        (user_root / "voices" / "uk" / "dictionary-voice.onnx.json").write_text(
            '{"language":{"code":"en_GB"},"espeak":{"voice":"en"}}', encoding="utf-8"
        )
        (user_root / "voices" / "us").mkdir(parents=True)
        (user_root / "voices" / "us" / "dictionary-voice.onnx.json").write_text(
            '{"language":{"code":"en_US"}}', encoding="utf-8"
        )
        preferences = user_data / "preferences.json"
        preferences.parent.mkdir(parents=True, exist_ok=True)
        preferences.write_text('{"prefer_recordings": true, "voice": "system"}\n', encoding="utf-8")
        preference_hash = file_sha256(preferences)

        staged_files = verify_pinned_tree(package_root, lock, runtime_manifest)
        make_read_only(package_root)
        before_paths = sorted(path.relative_to(package_root).as_posix() for path in package_root.rglob("*") if path.is_file())
        cache = user_data / "speech-cache"
        engine = SpeechEngine(package_root, cache, user_root=user_root)
        engine.recordings = OfflineRecordings()
        engine.quick_recording = lambda *_args: None
        urllib.request.urlopen = blocked_network
        socket.create_connection = blocked_network
        socket.socket.connect = blocked_network
        previous_path = os.environ.get("PATH", "")
        runner_crt = os.environ.get("WOER_TEST_CRT_PATH")
        runtime_search_path = [str(runtime_target)]
        if runner_crt:
            runner_crt_path = Path(runner_crt).resolve()
            if not runner_crt_path.is_dir() or runner_crt_path.is_relative_to(package_root.resolve()):
                raise AssertionError("Runner CRT must come from the Visual Studio test environment, outside the staged install tree")
            runtime_search_path.append(str(runner_crt_path))
        system_path = os.pathsep.join((*runtime_search_path, str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]))
        results = []
        try:
            if not engine.prefer_recordings:
                raise AssertionError("Smoke unexpectedly changed the live-recording preference")
            os.environ["PATH"] = system_path
            for accent, label in ((1, "uk"), (2, "us")):
                selected = engine._voice_folder(accent).resolve()
                expected_folder = (voices_target / label).resolve()
                if selected != expected_folder:
                    raise AssertionError(f"Partial user {label} directory masked the bundled voice")
                model, config, _voice_config, _upgraded, _config_hash = voice_files(selected, accent)
                output = engine.render("water", accent)
                if output.resolve().parent != cache.resolve():
                    raise AssertionError("Rendered PCM cache escaped the writable user cache")
                if engine.last_source is not None:
                    raise AssertionError("Offline smoke unexpectedly used a recording")
                summary = audio_summary(output, label)
                summary.update({
                    "voice_source": "bundled",
                    "revision": next(item["revision"] for item in lock["models"] if item["accent"] == label),
                    "model_sha256": file_sha256(model),
                    "config_sha256": file_sha256(config),
                })
                results.append(summary)
            if engine.prefer_recordings is not True:
                raise AssertionError("SpeechEngine changed the recording preference")
            if file_sha256(preferences) != preference_hash:
                raise AssertionError("SpeechEngine changed the preferences file")
            after_paths = sorted(path.relative_to(package_root).as_posix() for path in package_root.rglob("*") if path.is_file())
            if after_paths != before_paths:
                raise AssertionError("Synthesis modified the read-only install tree")
        finally:
            os.environ["PATH"] = previous_path
            engine.close()
            for proc in list(engine.processes):
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            restore_writable(package_root)

        # Preserve complete per-accent user overrides while falling back only
        # for the other incomplete accent.
        override_root = user_data / "custom-voice-test"
        custom_uk = override_root / "voices" / "uk"
        custom_uk.mkdir(parents=True)
        (custom_uk / "voice.onnx").write_bytes(b"fixture legacy model")
        (custom_uk / "voice.onnx.json").write_text(
            '{"language":{"code":"en_GB"}}', encoding="utf-8"
        )
        override_engine = SpeechEngine(package_root, cache, user_root=override_root)
        try:
            selected_custom = override_engine._voice_folder(1).resolve()
            if selected_custom != custom_uk.resolve():
                raise AssertionError("A complete legacy user voice pair no longer takes precedence")
            custom_model, custom_config, *_ = voice_files(selected_custom, 1)
            if custom_model.name != "voice.onnx" or custom_config.name != "voice.onnx.json":
                raise AssertionError("Legacy custom voice selection was not preserved")
            if override_engine._voice_folder(2).resolve() != (voices_target / "us").resolve():
                raise AssertionError("Per-accent fallback did not preserve the other bundled accent")
        finally:
            override_engine.close()

    return {
        "offline_recording_service_blocked": True,
        "msvc_crt_packaged": False,
        "runner_msvc_crt_path": os.environ.get("WOER_TEST_CRT_PATH"),
        "recording_preference_preserved": True,
        "preferences_file_preserved": True,
        "partial_user_pairs_fell_back_per_accent": True,
        "legacy_user_pair_override_preserved": True,
        "install_tree_read_only": True,
        "install_files_verified": len(staged_files),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = run_smoke(args)
    result["normal_app_path"] = "pronunciation.SpeechEngine.render"
    result["model_weights_uploaded"] = False
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

