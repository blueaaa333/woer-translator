$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath($env:GITHUB_WORKSPACE)
$runtimeRoot = Join-Path $root "build/voice-runtime"
$modelRoot = Join-Path $env:RUNNER_TEMP "woer-piper-voice-input"
$licenseReport = Join-Path $root "build/voice-licensing/voice-license-preflight.json"
$bundleRoot = Join-Path $root "build/voice-package"
$reportRoot = Join-Path $root "build/voice-package-review"
$dependencyReport = Join-Path $runtimeRoot "runtime-dependency-report.json"
$systemCrtReport = Join-Path $reportRoot "system-crt-prerequisite.json"
$officialRuntimeUrl = "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170"

foreach ($required in @($dependencyReport,$licenseReport,(Join-Path $modelRoot "speech/voices/uk/dictionary-voice.onnx"),
    (Join-Path $modelRoot "speech/voices/us/dictionary-voice.onnx"))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required pinned build input is missing: $required" }
}
$dependency = Get-Content -LiteralPath $dependencyReport -Raw | ConvertFrom-Json
$buildCrt = @($dependency.msvc_redist_files | Where-Object { $_.name -ieq "VCRUNTIME140.dll" } | Select-Object -First 1)
if ($buildCrt.Count -ne 1 -or -not $buildCrt[0].file_version) {
    throw "The runtime build report lacks the exact VCRUNTIME140.dll version used by the MSVC toolset"
}
$minimumRuntimeVersion = [Version]$buildCrt[0].file_version
$system32 = Join-Path $env:SystemRoot "System32"
$crtNames = @("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")
$systemCrtRecords = @()
foreach ($name in $crtNames) {
    $path = Join-Path $system32 $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "The runner does not have the required x64 system CRT file: $path"
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
    if ($signature.Status -ne "Valid" -or $subject -notmatch '(?i)(?:^|,\s*)(?:CN|O)=Microsoft Corporation(?:,|$)') {
        throw "System CRT signature is not valid Microsoft Authenticode: $name ($($signature.Status)) $subject"
    }
    $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($path)
    $fileVersion = [Version]$info.FileVersion
    if ($fileVersion -lt $minimumRuntimeVersion) {
        throw "System CRT is older than the runtime used to build Piper: $name $fileVersion < $minimumRuntimeVersion"
    }
    $systemCrtRecords += [ordered]@{
        name = $name; path = $path; bytes = (Get-Item -LiteralPath $path).Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        file_version = $info.FileVersion; signature = [string]$signature.Status; signer = $subject
    }
}
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
([ordered]@{
    tested_only = $true
    system_crt_root = $system32
    minimum_runtime_version_from_build = $minimumRuntimeVersion.ToString()
    files = $systemCrtRecords
    prerequisite_url = $officialRuntimeUrl
    note = "No CRT DLL or vc_redist installer is copied into the candidate package."
} | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $systemCrtReport -Encoding UTF8

$prepareArgs = @("scripts/prepare_voice_bundle.py", "--runtime-root", $runtimeRoot, "--model-root", $modelRoot,
    "--license-report", $licenseReport, "--output-root", $bundleRoot, "--lock", "scripts/voice_runtime_lock.json",
    "--report", (Join-Path $reportRoot "voice-bundle.json"))
python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw "Locked voice bundle staging failed: $LASTEXITCODE" }
$releaseArgs = @("scripts/build_release.py", "--voice-bundle-root", $bundleRoot,
    "--minimum-msvc-runtime-version", $minimumRuntimeVersion.ToString(), "--skip-portable")
python @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "Windows voice installer build failed: $LASTEXITCODE" }

$programFilesX86 = [Environment]::ExpandEnvironmentVariables("%ProgramFiles(x86)%")
$compiler = Join-Path $programFilesX86 "Inno Setup 6/ISCC.exe"
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw "Inno Setup compiler is missing: $compiler" }
$iss = Join-Path $root "packaging/windows.iss"
$version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw).Trim()
$requiredParts = $minimumRuntimeVersion.ToString().Split(".")
$minimumArgs = @()
$minimumNames = @("Major", "Minor", "Build", "Revision")
for ($i = 0; $i -lt 4; $i++) { $minimumArgs += "/DMsvcRuntimeMinimum$($minimumNames[$i])=$($requiredParts[$i])" }
$fixtureCommon = @("/DAppVersion=$version", "/DRequireMsvcRuntime=1", "/DProbeInstaller=1") + $minimumArgs
$missingArgs = $fixtureCommon + @("/DProbeForceMissingMsvcRuntime=1", $iss)
& $compiler @missingArgs
if ($LASTEXITCODE -ne 0) { throw "Inno missing-CRT fixture compile failed: $LASTEXITCODE" }
$oldArgs = @("/DAppVersion=$version", "/DRequireMsvcRuntime=1", "/DProbeInstaller=1",
    "/DMsvcRuntimeMinimumMajor=99", "/DMsvcRuntimeMinimumMinor=0",
    "/DMsvcRuntimeMinimumBuild=0", "/DMsvcRuntimeMinimumRevision=0", $iss)
& $compiler @oldArgs
if ($LASTEXITCODE -ne 0) { throw "Inno too-old-CRT fixture compile failed: $LASTEXITCODE" }

$candidateSetup = Join-Path $root "release-assets/WoerTranslator-$version-Windows-x64-Setup.exe"
$missingSetup = Join-Path $root "release-assets/WoerTranslator-MsvcRuntime-Missing-Probe.exe"
$tooOldSetup = Join-Path $root "release-assets/WoerTranslator-MsvcRuntime-TooOld-Probe.exe"
$probeScript = Join-Path $root "tests/run_windows_voice_installer_probe.ps1"
& $probeScript -CandidateSetup $candidateSetup -MissingRuntimeSetup $missingSetup -TooOldRuntimeSetup $tooOldSetup -MinimumRuntimeVersion $minimumRuntimeVersion.ToString() -ReportRoot $reportRoot
