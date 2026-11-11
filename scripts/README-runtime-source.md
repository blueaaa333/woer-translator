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
DLLs, the Windows validation artifact includes the unmodified files from that
runner's Visual Studio 2022 `Microsoft.VC143.CRT` redistributable directory,
its `redist.txt`, and `msvc-redist-evidence.json`. That report records the
selected redist version and exact source directory, a SHA-256 for `redist.txt`,
the official Microsoft Visual C++ Runtime 2015-2022 license URL and downloaded
document hash, and the file version, SHA-256, and verified Microsoft
Authenticode signer for each DLL.

Microsoft's official [Visual Studio 2022 redistribution list](https://learn.microsoft.com/visualstudio/releases/2022/redistribution)
states that REDIST.txt is the distributable list referenced by the applicable
Visual Studio license terms; the list is not itself the license. The applicable
[Visual C++ Runtime 2015-2022 license terms](https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/)
and Microsoft's [redistribution guidance](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files)
are recorded with the artifact. These are Microsoft redistributables, not
MIT/GPL components. The test record does not certify the rights of any
particular publisher. Windows API-set/system imports remain classified
separately from bundled MSVC CRT files; the runtime is rejected if any
non-system import remains unresolved.

eSpeak NG is GPL-3.0-or-later. Any redistributed runtime must be accompanied
by the matching source archive and notices generated with that runtime.
This is a source/provenance record, not a non-infringement warranty.

