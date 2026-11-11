# Piper runtime source bundle

This archive contains source ZIPs created from all six exact top-level commits
in voice_runtime_lock.json and separately archived, locked source for every
gitlink in those projects (including six ONNX Runtime gitlinks and nested
gitlinks in the pinned ONNX and protobuf sources). It also
includes the build/archive scripts, a source manifest, and per-component
license/notice files. The source archives exclude `.onnx` and `.ort`
test/model files; the CI artifact must not contain the selected voice weights.
The runtime uses the official, unmodified ONNX Runtime 1.14.1 Windows x64
binary, with its URL, observed SHA-256, license and third-party notices
recorded separately. The SHA is an observed CI download hash because the
upstream release API did not publish one.

The build script generates a temporary CMake project hook that adds the
`SPDLOG_FMT_EXTERNAL` definition to Piper targets. It does not replace the
compiler's default exception, warning or runtime flags. The hook is generated
from the archived build script and is not a separate untracked patch.

The build also inspects the PE import table. If the binaries require MSVC CRT
DLLs, the Windows validation artifact includes the files from that runner's
Visual Studio 2022 `Microsoft.VC143.CRT` redistributable directory, its
`redist.txt`, and a dependency report with version and per-file SHA-256 values.
Those Microsoft redistributables are distributed under Microsoft's terms and
are not part of this open-source source archive. The runtime is rejected if
any non-system import remains unresolved.

eSpeak NG is GPL-3.0-or-later. Any redistributed runtime must be accompanied
by the matching source archive and notices generated with that runtime.
This is a source/provenance record, not a non-infringement warranty.
