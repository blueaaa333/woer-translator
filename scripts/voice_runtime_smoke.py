"""Exercise the application's SpeechEngine against a staged read-only bundle."""
import argparse
import errno
import getpass
import hashlib
import json
import os
import re
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


def current_process_sid():
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True, capture_output=True, text=True,
    )
    matches = re.findall(r"S-1-\d+(?:-\d+)+", result.stdout)
    if len(matches) != 1:
        raise RuntimeError(f"Could not identify one current process SID: {result.stdout!r}")
    return matches[0]


def is_access_denied(error):
    return getattr(error, "winerror", None) == 5 or error.errno in (errno.EACCES, errno.EPERM)


def acl_snapshot(path):
    path = Path(path)
    icacls_command = ["icacls", str(path)]
    icacls = subprocess.run(icacls_command, capture_output=True, text=True)
    if icacls.returncode != 0:
        raise RuntimeError(
            f"icacls failed for {path}: exit={icacls.returncode}; "
            f"stdout={icacls.stdout!r}; stderr={icacls.stderr!r}"
        )
    environment = os.environ.copy()
    environment["WOER_ACL_PROBE_PATH"] = str(path)
    powershell_script = (
        "$acl = Get-Acl -LiteralPath $env:WOER_ACL_PROBE_PATH; "
        "$rules = @($acl.Access | ForEach-Object { "
        "[pscustomobject]@{ identity=$_.IdentityReference.Value; "
        "rights=$_.FileSystemRights.ToString(); "
        "type=$_.AccessControlType.ToString(); inherited=$_.IsInherited; "
        "inheritance=$_.InheritanceFlags.ToString(); "
        "propagation=$_.PropagationFlags.ToString() } }); "
        "[pscustomobject]@{ path=$acl.Path; owner=$acl.Owner; "
        "are_access_rules_protected=$acl.AreAccessRulesProtected; "
        "access=$rules } | ConvertTo-Json -Depth 6 -Compress"
    )
    get_acl_command = ["pwsh", "-NoProfile", "-Command", powershell_script]
    get_acl = subprocess.run(get_acl_command, env=environment, capture_output=True, text=True)
    if get_acl.returncode != 0:
        raise RuntimeError(
            f"Get-Acl failed for {path}: exit={get_acl.returncode}; "
            f"stdout={get_acl.stdout!r}; stderr={get_acl.stderr!r}"
        )
    try:
        acl_data = json.loads(get_acl.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Get-Acl returned invalid JSON for {path}: {get_acl.stdout!r}") from exc
    return {
        "path": str(path),
        "icacls_command": icacls_command,
        "icacls_exit_code": icacls.returncode,
        "icacls_stdout": icacls.stdout,
        "icacls_stderr": icacls.stderr,
        "get_acl_command": get_acl_command,
        "get_acl": acl_data,
    }


def acl_targets(root):
    root = Path(root)
    targets = [root]
    for label in ("uk", "us"):
        voice_folder = root / "speech" / "voices" / label
        targets.append(voice_folder)
        targets.extend(voice_folder / name for name in (
            "dictionary-voice.onnx",
            "dictionary-voice.onnx.json",
        ))
    return [path for path in targets if path.exists()]


def restore_writable(root):
    root = Path(root)
    if not root.exists():
        return
    sid = current_process_sid()
    command = [
        "icacls", str(root), "/inheritance:e", "/grant:r",
        f"*{sid}:(OI)(CI)(F)",
    ]
    subprocess.run(command, check=False, capture_output=True, text=True)


def make_read_only(root, writable_cache):
    root = Path(root)
    sid = current_process_sid()
    before_configs = []
    for config in sorted(root.rglob("*.onnx.json")):
        data = json.loads(config.read_text(encoding="utf-8"))
        before_configs.append({
            "path": str(config),
            "bytes": config.stat().st_size,
            "sha256": file_sha256(config),
            "language_code": data.get("language", {}).get("code"),
        })
    evidence = {
        "root": str(root),
        "current_process_sid": sid,
        "before_config_read": before_configs,
        "before_acl": [acl_snapshot(path) for path in acl_targets(root)],
    }
    commands = [
        ["icacls", str(root), "/inheritance:r"],
        ["icacls", str(root), "/remove:g", "*S-1-3-4", "*S-1-5-32-544"],
        ["icacls", str(root), "/grant:r", f"*{sid}:(OI)(CI)(RX)"],
    ]
    command_results = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        command_results.append({
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
        if result.returncode != 0:
            evidence["set_acl_commands"] = command_results
            restore_writable(root)
            raise RuntimeError(f"Could not set temporary package ACL: {json.dumps(evidence, sort_keys=True)}")
    evidence["set_acl_commands"] = command_results

    try:
        evidence["after_acl"] = [acl_snapshot(path) for path in acl_targets(root)]
        checks = {
            "readable_configs": [],
            "readable_models": [],
            "voice_directory_creation_denied": [],
            "model_write_open_denied": [],
        }
        config_paths = sorted(root.rglob("*.onnx.json"))
        model_paths = sorted(root.rglob("*.onnx"))
        if len(config_paths) != 2 or len(model_paths) != 2:
            raise AssertionError(
                f"Expected two bundled model/config pairs for ACL checks; "
                f"models={len(model_paths)} configs={len(config_paths)}"
            )
        for config in config_paths:
            data = json.loads(config.read_text(encoding="utf-8"))
            checks["readable_configs"].append({
                "path": str(config),
                "bytes": config.stat().st_size,
                "language_code": data.get("language", {}).get("code"),
            })
        for model in model_paths:
            with model.open("rb") as stream:
                first_byte = stream.read(1)
            if not first_byte:
                raise AssertionError(f"Bundled model cannot be read or is empty: {model}")
            checks["readable_models"].append({
                "path": str(model),
                "bytes": model.stat().st_size,
            })
        for label in ("uk", "us"):
            voice_folder = root / "speech" / "voices" / label
            probe = voice_folder / "readonly-create-probe.tmp"
            try:
                probe.write_bytes(b"must be denied")
            except OSError as exc:
                if not is_access_denied(exc):
                    raise AssertionError(
                        f"Voice folder creation failed for a non-access reason: {voice_folder}: {exc}"
                    ) from exc
                checks["voice_directory_creation_denied"].append({
                    "path": str(voice_folder),
                    "error": f"{type(exc).__name__}: {exc}",
                    "winerror": getattr(exc, "winerror", None),
                })
            else:
                probe.unlink(missing_ok=True)
                raise AssertionError(f"Read-only voice directory still allows file creation: {voice_folder}")
        for model in model_paths:
            try:
                with model.open("r+b"):
                    pass
            except OSError as exc:
                if not is_access_denied(exc):
                    raise AssertionError(
                        f"Model write-open failed for a non-access reason: {model}: {exc}"
                    ) from exc
                checks["model_write_open_denied"].append({
                    "path": str(model),
                    "error": f"{type(exc).__name__}: {exc}",
                    "winerror": getattr(exc, "winerror", None),
                })
            else:
                raise AssertionError(f"Read-only model still opens for writing: {model}")
        writable_cache = Path(writable_cache)
        writable_cache.mkdir(parents=True, exist_ok=True)
        cache_probe = writable_cache / "readonly-package-cache-probe.tmp"
        cache_probe.write_bytes(b"outside package")
        cache_probe.unlink()
        checks["outside_cache_writable"] = str(writable_cache)
        evidence["checks"] = checks
        return evidence
    except Exception as exc:
        try:
            evidence["failure_acl"] = [acl_snapshot(path) for path in acl_targets(root)]
        except Exception as acl_error:
            evidence["failure_acl_error"] = f"{type(acl_error).__name__}: {acl_error}"
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        restore_writable(root)
        raise RuntimeError(
            f"Temporary package ACL validation failed: {json.dumps(evidence, sort_keys=True)}"
        ) from exc


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



def same_directory(left, right):
    left = Path(left)
    right = Path(right)
    if left.exists() and right.exists():
        try:
            return left.samefile(right)
        except OSError:
            pass
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def voice_candidate_diagnostic(folder, accent):
    folder = Path(folder)
    managed_model = folder / "dictionary-voice.onnx"
    managed_config = folder / "dictionary-voice.onnx.json"
    detail = {
        "folder": str(folder),
        "managed_model_exists": managed_model.is_file(),
        "managed_model_bytes": managed_model.stat().st_size if managed_model.is_file() else None,
        "managed_config_exists": managed_config.is_file(),
        "managed_config_bytes": managed_config.stat().st_size if managed_config.is_file() else None,
    }
    if managed_config.is_file():
        try:
            data = json.loads(managed_config.read_text(encoding="utf-8"))
            detail["managed_language_code"] = data.get("language", {}).get("code")
        except Exception as exc:
            detail["managed_config_error"] = f"{type(exc).__name__}: {exc}"
    try:
        model, config, data, upgraded, config_hash = voice_files(folder, accent)
        detail["voice_files"] = {
            "ok": True,
            "model": str(model),
            "model_bytes": model.stat().st_size,
            "config": str(config),
            "language_code": data.get("language", {}).get("code"),
            "upgraded": upgraded,
            "config_sha256": config_hash,
        }
    except Exception as exc:
        detail["voice_files"] = {
            "ok": False,
            "exception": f"{type(exc).__name__}: {exc}",
        }
    return detail


def download_verified_config(model):
    item = next((entry for entry in model["files"] if entry["name"] == "dictionary-voice.onnx.json"), None)
    if item is None:
        raise ValueError(f"Locked config is missing for {model['accent']}")
    request = urllib.request.Request(
        item["url"],
        headers={"User-Agent": "WoerTranslator-voice-selection-probe/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(item["bytes"] + 1)
    actual = hashlib.sha256(data).hexdigest()
    if len(data) != item["bytes"] or actual != item["sha256"]:
        raise ValueError(
            f"Config verification failed for {model['accent']}: "
            f"bytes={len(data)} sha256={actual}"
        )
    return item, data


def run_selection_preflight(args):
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    verified_configs = {}
    for model in lock["models"]:
        item, data = download_verified_config(model)
        verified_configs[model["accent"]] = (item, data)

    with tempfile.TemporaryDirectory(prefix="woer-voice-selection-") as temp:
        scratch = Path(temp)
        package_root = scratch / "Woer Install 汉字 Space"
        user_root = scratch / "用户 数据 Space" / "speech"
        voices_target = package_root / "speech" / "voices"
        config_evidence = []
        for model in lock["models"]:
            accent = model["accent"]
            item, data = verified_configs[accent]
            bundled = voices_target / accent
            bundled.mkdir(parents=True, exist_ok=True)
            model_path = bundled / "dictionary-voice.onnx"
            # Selection only needs a present, over-threshold bundle model. This
            # sparse placeholder is never passed to Piper or included in artifacts.
            with model_path.open("wb") as stream:
                stream.truncate(1_000_001)
            (bundled / "dictionary-voice.onnx.json").write_bytes(data)
            config_evidence.append({
                "accent": accent,
                "config_bytes": len(data),
                "config_sha256": item["sha256"],
                "config_url": item["url"],
            })

        # Match the real regression fixture: UK has a truncated model plus a
        # valid config; US has only a valid config. Neither user pair is complete.
        partial_uk = user_root / "voices" / "uk"
        partial_uk.mkdir(parents=True)
        (partial_uk / "dictionary-voice.onnx").write_bytes(b"truncated model")
        (partial_uk / "dictionary-voice.onnx.json").write_bytes(verified_configs["uk"][1])
        partial_us = user_root / "voices" / "us"
        partial_us.mkdir(parents=True)
        (partial_us / "dictionary-voice.onnx.json").write_bytes(verified_configs["us"][1])

        cache = scratch / "user-cache"
        acl_evidence = make_read_only(package_root, cache)
        print("Selection-only temporary ACL evidence: " + json.dumps(acl_evidence, sort_keys=True))
        engine = None
        results = []
        failures = []
        try:
            engine = SpeechEngine(package_root, cache, user_root=user_root)
            for accent, label in ((1, "uk"), (2, "us")):
                user_folder = user_root / "voices" / label
                bundled_folder = voices_target / label
                selected = engine._voice_folder(accent)
                same_as_bundle = same_directory(selected, bundled_folder)
                result = {
                    "accent": label,
                    "user_root": str(engine.root),
                    "bundle_root": str(engine.bundle_root),
                    "user_candidate": voice_candidate_diagnostic(user_folder, accent),
                    "bundled_candidate": voice_candidate_diagnostic(bundled_folder, accent),
                    "selected": str(selected),
                    "expected": str(bundled_folder),
                    "selected_is_expected_directory": same_as_bundle,
                }
                results.append(result)
                if not same_as_bundle:
                    failures.append(label)
        finally:
            if engine is not None:
                engine.close()
            restore_writable(package_root)

    result = {
        "passed": not failures,
        "read_only_acl_evidence": acl_evidence,
        "selection_only": True,
        "normal_app_path": "pronunciation.SpeechEngine._voice_folder",
        "model_weights_downloaded": False,
        "bundle_models_are_sparse_selection_placeholders": True,
        "partial_user_fixture": {
            "uk_model_bytes": len(b"truncated model"),
            "uk_config_sha256": verified_configs["uk"][0]["sha256"],
            "us_model_exists": False,
            "us_config_sha256": verified_configs["us"][0]["sha256"],
        },
        "verified_configs": config_evidence,
        "results": results,
        "failed_accents": failures,
    }
    return result

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
        cache = user_data / "speech-cache"
        acl_evidence = make_read_only(package_root, cache)
        print("Full-smoke temporary ACL evidence: " + json.dumps(acl_evidence, sort_keys=True))
        before_paths = sorted(path.relative_to(package_root).as_posix() for path in package_root.rglob("*") if path.is_file())
        engine = None
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
            engine = SpeechEngine(package_root, cache, user_root=user_root)
            engine.recordings = OfflineRecordings()
            engine.quick_recording = lambda *_args: None
            urllib.request.urlopen = blocked_network
            socket.create_connection = blocked_network
            socket.socket.connect = blocked_network
            if not engine.prefer_recordings:
                raise AssertionError("Smoke unexpectedly changed the live-recording preference")
            os.environ["PATH"] = system_path
            for accent, label in ((1, "uk"), (2, "us")):
                selected_path = engine._voice_folder(accent)
                expected_folder = voices_target / label
                if not same_directory(selected_path, expected_folder):
                    diagnostics = {
                        "accent": label,
                        "user_root": str(engine.root),
                        "bundle_root": str(engine.bundle_root),
                        "selected": str(selected_path),
                        "expected": str(expected_folder),
                        "user_candidate": voice_candidate_diagnostic(engine.root / "voices" / label, accent),
                        "bundled_candidate": voice_candidate_diagnostic(expected_folder, accent),
                    }
                    raise AssertionError(
                        f"Partial user {label} directory masked the bundled voice: "
                        f"{json.dumps(diagnostics, sort_keys=True)}"
                    )
                selected = selected_path.resolve()
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
            if engine is not None:
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
            selected_custom = override_engine._voice_folder(1)
            if not same_directory(selected_custom, custom_uk):
                raise AssertionError("A complete legacy user voice pair no longer takes precedence")
            custom_model, custom_config, *_ = voice_files(selected_custom, 1)
            if custom_model.name != "voice.onnx" or custom_config.name != "voice.onnx.json":
                raise AssertionError("Legacy custom voice selection was not preserved")
            if not same_directory(override_engine._voice_folder(2), voices_target / "us"):
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
        "read_only_acl_evidence": acl_evidence,
        "install_files_verified": len(staged_files),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-only", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.selection_only:
        result = run_selection_preflight(args)
    else:
        for name in ("runtime", "models", "build_root"):
            if getattr(args, name) is None:
                parser.error(f"--{name.replace('_', '-')} is required unless --selection-only is used")
        result = run_smoke(args)
        result["normal_app_path"] = "pronunciation.SpeechEngine.render"
        result["model_weights_uploaded"] = False
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if args.selection_only and not result["passed"]:
        raise SystemExit(f"Voice selection preflight failed for: {', '.join(result['failed_accents'])}")


if __name__ == "__main__":
    main()

