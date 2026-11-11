$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath($env:GITHUB_WORKSPACE)
$runtimeRoot = Join-Path $root "build/voice-runtime"
$modelRoot = Join-Path $env:RUNNER_TEMP "woer-piper-voice-input"
$licenseReport = Join-Path $root "build/voice-licensing/voice-license-preflight.json"
$bundleRoot = Join-Path $root "build/voice-package"
$reportRoot = Join-Path $root "build/voice-package-review"
$dependencyReport = Join-Path $runtimeRoot "runtime-dependency-report.json"
$eula = Join-Path $env:RUNNER_TEMP "Microsoft-Visual-C-Runtime-2015-2022-License.docx"

foreach ($required in @($dependencyReport,$licenseReport,$eula,(Join-Path $modelRoot "speech/voices/uk/dictionary-voice.onnx"),
    (Join-Path $modelRoot "speech/voices/us/dictionary-voice.onnx"))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required pinned build input is missing: $required" }
}
$dependency = Get-Content -LiteralPath $dependencyReport -Raw | ConvertFrom-Json
$crtSource = $dependency.runner_msvc_redist_directory
if (-not $crtSource -or -not (Test-Path -LiteralPath $crtSource -PathType Container)) {
    throw "Probe build cannot locate the exact runner CRT directory in runtime-dependency-report.json"
}
$crtNames = @("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")
$crtRecords = @()
foreach ($name in $crtNames) {
    $path = Join-Path $crtSource $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Runner CRT directory lacks required import: $name" }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
    if ($signature.Status -ne "Valid" -or $subject -notmatch '(?i)(?:^|,\s*)(?:CN|O)=Microsoft Corporation(?:,|$)') {
        throw "Runner CRT signature is not valid Microsoft Authenticode: $name ($($signature.Status)) $subject"
    }
    $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($path)
    $crtRecords += [ordered]@{
        name = $name; path = $path; bytes = (Get-Item -LiteralPath $path).Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        file_version = $info.FileVersion; signature = [string]$signature.Status; signer = $subject
    }
}
$redistNotice = Join-Path $runtimeRoot "licenses/msvc-redist/redist.txt"
$redistEvidencePath = Join-Path $runtimeRoot "licenses/msvc-redist/msvc-redist-evidence.json"
if (-not (Test-Path -LiteralPath $redistEvidencePath -PathType Leaf)) {
    throw "The Microsoft CRT source evidence is missing from the runtime build output"
}
$redistEvidence = Get-Content -LiteralPath $redistEvidencePath -Raw | ConvertFrom-Json
$redistNoticePresent = Test-Path -LiteralPath $redistNotice -PathType Leaf
$redistNoticeHash = $null
if ($redistNoticePresent) {
    $redistNoticeHash = (Get-FileHash -LiteralPath $redistNotice -Algorithm SHA256).Hash.ToLowerInvariant()
}
if ([bool]$redistEvidence.redist_txt_present_in_installation -ne [bool]$redistNoticePresent) {
    throw "Staged redist.txt presence does not match msvc-redist-evidence.json"
}
if ($redistNoticeHash -and $redistEvidence.redist_txt_sha256 -and
    $redistNoticeHash -ne [string]$redistEvidence.redist_txt_sha256) {
    throw "Staged redist.txt hash does not match msvc-redist-evidence.json"
}
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
([ordered]@{
    tested_only = $true
    visual_studio_redist_version = $dependency.visual_studio_redist_version
    runner_redist_directory = $crtSource
    redist_txt_present_in_installation = [bool]$redistNoticePresent
    redist_txt_sha256 = $redistNoticeHash
    eula_source = "https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx"
    eula_sha256 = (Get-FileHash -LiteralPath $eula -Algorithm SHA256).Hash.ToLowerInvariant()
    visual_studio_2022_redistribution_list_url = $redistEvidence.visual_studio_2022_redistribution_list_url
    visual_studio_2022_redistribution_list_snapshot_sha256 = $redistEvidence.visual_studio_2022_redistribution_list_snapshot_sha256
    msvc_redist_evidence_sha256 = (Get-FileHash -LiteralPath $redistEvidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
    files = $crtRecords
    redistribution_rights = "not established by this CI package probe"
} | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath (Join-Path $reportRoot "crt-source-inspection.json") -Encoding UTF8

python scripts/prepare_voice_bundle.py --runtime-root $runtimeRoot --model-root $modelRoot `
    --license-report $licenseReport --output-root $bundleRoot --crt-source $crtSource --crt-eula $eula `
    --lock scripts/voice_runtime_lock.json --report (Join-Path $reportRoot "voice-bundle.json")
if ($LASTEXITCODE -ne 0) { throw "Locked voice bundle staging failed: $LASTEXITCODE" }
python scripts/build_release.py --voice-bundle-root $bundleRoot --skip-portable --allow-test-only-crt
if ($LASTEXITCODE -ne 0) { throw "Windows voice installer build failed: $LASTEXITCODE" }

$setup = Join-Path $root "release-assets/WoerTranslator-0.3.22-Windows-x64-Setup.exe"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw "Inno Setup did not create the candidate installer" }
$probeScript = Join-Path $root "tests/run_windows_voice_installer_probe.ps1"
& $probeScript -CandidateSetup $setup -ReportRoot $reportRoot

