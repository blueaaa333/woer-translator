# Voice bundle proposal

Temporary branch probe candidate. This branch is for CI investigation only;
it is not a release and changes nothing on main. The tests use small synthetic
files; they do not validate model weights or runtime binaries.

## What is prepared

- scripts/voice_runtime_lock.json pins the two voice asset URLs, byte counts,
  SHA-256 values, Hugging Face revision, and six source dependency commits.
- scripts/fetch_pinned_voices.py downloads only the two selected public voices;
  it never fetches the legacy opaque Piper Windows ZIP.
- scripts/build_piper_runtime.ps1 contains Windows source-build steps and stops
  when the ONNX Runtime binary SHA-256 is not reviewed and entered in the lock.
- scripts/archive_piper_sources.ps1 archives the selected source commits and
  license files next to the generated runtime.
- scripts/voice_runtime_smoke.py is the intended offline UK/US WAV smoke.
- .github/workflows/voice-runtime-probe.yml is a temporary Windows 2022
  validation workflow with contents:read and a 14-day artifact only.
- scripts/voice_bundle.py and tests/test_voice_bundle.py exercise per-accent
  complete-pair selection, incomplete-user fallback, runtime resolution,
  user-cache output placement, and exact file allowlisting.

## Review gates

1. ONNX Runtime 1.14.1 release metadata returned no asset digest. DiscoverOrt
   can record the downloaded file's SHA-256, but a human must review it and add
   it to the lock before BuildRuntime will proceed.
2. The fixed Hugging Face revision page could not be reopened through the web
   tool. The accessible v1.0.0 repository/model-card pages show MIT metadata and
   LibriVox public-domain dataset statements; verify those claims at revision
   5041a7a49ae5b3a0f30e6837769eb03fdbb231bd before VoiceSmoke or redistribution.
3. No MSVC/CMake toolchain is installed in this workspace. Source compilation,
   runtime source-closure, actual offline dual-voice synthesis, installer
   upgrade and read-only install-tree checks remain unverified.
4. eSpeak NG is GPL-3.0-or-later. The generated source archive and extracted
   notices must match the built DLLs before any release.

The workflow is limited to the approved temporary test scope:

- Repository: blueaaa333/woer-translator
- Temporary branch: codex/voice-bundle-runtime-probe, based on current public
  main; do not edit VERSION or release files.
- Workflow: .github/workflows/voice-runtime-probe.yml on windows-2022.
- Artifact: temporary 14-day source/runtime verification outputs and notices.
  Voice model weights are consumed by the smoke job but are not uploaded.
- No Release creation, update-feed change, package publish, or user data.

The current updater accepts installers up to 400 MiB. The final Windows package
size is not known until it is built, so retain an actual asset-size check.
