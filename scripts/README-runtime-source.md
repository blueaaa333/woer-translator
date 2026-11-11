# Piper runtime source bundle

This archive contains source ZIPs created from all six exact top-level commits
in voice_runtime_lock.json and separately archived, locked source for every
gitlink in those projects (including all six ONNX Runtime gitlinks). It also
includes the build/archive scripts, a source manifest, and per-component
license/notice files. The source archives exclude `.onnx` and `.ort`
test/model files; the CI artifact must not contain the selected voice weights.
The runtime uses the official, unmodified
ONNX Runtime 1.14.1 Windows x64 binary, with its URL, observed SHA-256, license
and third-party notices recorded separately.

eSpeak NG is GPL-3.0-or-later. Any redistributed runtime must be accompanied
by the matching source archive and notices generated with that runtime.
This is a source/provenance record, not a non-infringement warranty.
