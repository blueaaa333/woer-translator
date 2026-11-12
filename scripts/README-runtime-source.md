# Piper runtime source bundle

This ZIP is a separate, version-matched GitHub Release asset named
WoerTranslator-<version>-piper-runtime-source.zip; it is not embedded in the
Windows installer. The installer retains model-card and component notices,
source manifest, archive hash and a link to the matching release asset.

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
DLLs, this probe verifies the runner's Visual Studio 2022
`Microsoft.VC143.CRT` directory and uses that directory on `PATH` for smoke
testing. It does not copy Microsoft CRT binaries into the public artifact.
`msvc-redist-evidence.json` records the redist version and exact source
directory, the official Microsoft Visual C++ Runtime 2015-2022 license URL
and downloaded document hash, and the file version, SHA-256, and verified
Microsoft Authenticode signer for each runner DLL. If `redist.txt` exists in
the runner installation, its hash is recorded. If it does not, the report
records its absence and the artifact retains the official Microsoft
redistribution-list URL/hash instead.

Microsoft's official [Visual Studio 2022 redistribution list](https://learn.microsoft.com/visualstudio/releases/2022/redistribution)
states that REDIST.txt is the distributable list referenced by the applicable
Visual Studio license terms; the list is not itself the license. The applicable
[Visual C++ Runtime 2015-2022 license terms](https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/)
and Microsoft's [redistribution guidance](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files)
are recorded with the artifact. These are Microsoft redistributables, not
MIT/GPL components. The installer does not redistribute Microsoft CRT. It checks for an installed x64 system runtime at least 14.44.35211.0 and points users to Microsoft's official installation page if needed. CI smoke was run on a runner that already had a compatible system CRT; a clean machine without it is not covered. Windows System32 and API-set imports remain separate
from the runner CRT and from bundled files.

eSpeak NG is GPL-3.0-or-later. Any redistributed runtime must be accompanied
by the matching source archive and notices generated with that runtime.
This is a source/provenance record, not a non-infringement warranty.



