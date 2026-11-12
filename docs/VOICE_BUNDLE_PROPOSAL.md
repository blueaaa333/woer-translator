# Windows bundled voice release candidate

This document records the review candidate on the temporary test branch. The proposed release is v0.3.23; main, VERSION, update feed and formal Releases remain unchanged.

The Windows x64 installer packages the locked UK and US voices, model cards and the source-built Piper runtime. The same Windows build emits a version-named piper-runtime-source.zip and a small report binding filename, size and SHA-256 to that build. The full source archive is a separate same-version Release asset, not part of the installer; the installer retains the license notices, model provenance and release-asset link. Release staging includes the source ZIP in SHA256SUMS.txt and the release notes. The in-app update feed continues to contain only the three platform installers.

The installer does not bundle Microsoft CRT. Inno checks for x64 Microsoft Visual C++ Runtime 14.44.35211.0 or newer before modifying the installation directory, then directs users to Microsoft's official page if it is missing. CI checks use a runner with a compatible system runtime; a clean machine without it remains outside the verified case. Mac continues to use the built-in system voices.

The previous Windows probe passed actual offline UK/US SpeechEngine synthesis, initial install, upgrade over v0.3.22, partial-user-model fallback, a read-only Unicode install path, and preservation of preferences and wordbook. Moving the source ZIP out of the install tree changes the package layout, so the updated candidate CI must repeat build, install, upgrade, offline rendering, size/hash and source-asset staging checks before release review. This candidate is not a publication result.


