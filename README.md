# Temporary Piper runtime probe

This branch validates a test-only Windows runtime. It is not a release and
does not modify `main`, `VERSION`, the update feed, or a formal package. The
CI workflow downloads public model weights to runner temp, uses them for the
smoke, and excludes them and synthesized audio from artifacts.

## Current evidence

- SourceArchive passed in run `42988040804`; the archive verifier checks six
  top-level projects and all locked nested gitlinks. It excludes ONNX weights.
- BuildRuntime passed in run `42992174074` on `windows-2022`. Piper was built
  from locked sources, PE import closure resolved, and the staged CLI returned
  version `1.2.0`. The runtime/source artifact uploaded successfully. VoiceSmoke
  then failed before render because the readonly ACL probe still allowed a new
  file in the package root; the next run uses an explicit deny ACE and verifies
  both creating and modifying files are blocked.
- The fixed HF revision `5041a7a49ae5b3a0f30e6837769eb03fdbb231bd` was read in
  CI. Its root README declared MIT and the header revision matched. The two
  selected model cards matched their lock SHA-256 values and state that
  LibriVox recordings are public domain in the United States. Astra approved
  that evidence for this CI test only; it is not formal release approval.
- The license artifact preserves the full pinned README, both raw model cards,
  the complete standard MIT terms, source URLs, revision headers and file
  hashes. It reports actual copyright lines when present and does not invent
  an owner or year. The model weights are not in this artifact.
- Run `42992174074` read the pinned HF revision and the SHA-pinned SPDX MIT
  template, but report generation ended with a `NameError` caused by a field
  placed in the wrong object. That field is corrected for the next run.
- The official ONNX Runtime v1.14.1 release API lists the Windows archive as
  41,748,936 bytes but publishes no digest. CI observed SHA-256
  `1243f2c505de8845b6927ae1cbde75b9372f16965c6b2c8db2279f385003fd85` over
  HTTPS; this is an observed hash, not an upstream-published checksum.

## Next CI checks

The candidate updates the production `SpeechEngine` to select each complete
user voice pair independently and fall back to the bundled pair when a managed
user model is truncated or incomplete. Piper writes temporary WAV files under
the writable user cache, even when the installed runtime tree is read-only.
VoiceSmoke calls `pronunciation.SpeechEngine.render()` with the actual app
imports and declared OpenCC dependency, preserves the live-recording preference
and preferences file, verifies pinned model/config/runtime hashes, and renders
both accents with the recording service and network blocked. It also checks a
complete legacy user voice pair remains an override.

The build step inspects PE imports, packages only missing MSVC CRT redistributable
files from the same runner's licensed Visual Studio redist folder with its
`redist.txt`, and fails if another non-system dependency remains unresolved.
The next run must provide real dependency, source archive and non-silent PCM
evidence. Windows installer integration, upgrade preservation and package size
remain unverified; the existing updater's stated maximum is 400 MiB.

## Authorized scope

- Repository: `blueaaa333/woer-translator`
- Branch: `codex/voice-bundle-runtime-probe`
- Workflow: `.github/workflows/voice-runtime-probe.yml`, Windows 2022
- Artifacts: source archive, build/runtime notices, dependency report, license
  evidence JSON and short smoke report, retained for 14 days
- Excluded: model weights, synthesized audio, installers and private user data
- No Release creation, update-feed change, package publication or `main` edits
