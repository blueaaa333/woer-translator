param(
    [ValidateSet("DiscoverOrt", "SourceArchive", "BuildRuntime", "VoiceSmoke", "TestPeDependencyRecords", "TestMsvcRedistDiscovery")]
    [string]$Mode = "DiscoverOrt",
    [string]$LockPath = (Join-Path $PSScriptRoot "voice_runtime_lock.json"),
    [string]$SourceRoot = (Join-Path $env:RUNNER_TEMP "woer-piper-source"),
    [string]$OutputRoot = (Join-Path $env:GITHUB_WORKSPACE "build/voice-runtime")
)

$ErrorActionPreference = "Stop"
$lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$runtime = $lock.runtime
$work = Join-Path $env:RUNNER_TEMP "woer-piper-build"
$script:RunnerMsvcCrtPath = $null

function Invoke-Native([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File exited with code $LASTEXITCODE" }
}

function Get-Source([string]$Name) {
    $items = @($runtime.sources | Where-Object name -eq $Name)
    if ($items.Count -ne 1) { throw "Expected one locked source for $Name" }
    $item = $items[0]
    $directory = Join-Path $SourceRoot $Name
    if (-not (Test-Path -LiteralPath $directory)) {
        Invoke-Native "git" @("clone", "--filter=blob:none", "--no-checkout", "--depth", "1", $item.repository, $directory)
    }
    Invoke-Native "git" @("-C", $directory, "fetch", "--depth", "1", "origin", $item.commit)
    Invoke-Native "git" @("-C", $directory, "checkout", "--detach", "FETCH_HEAD")
    $actual = (& git -C $directory rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $item.commit) { throw "Commit mismatch for $Name" }
    return $directory
}

function Build-CMake([string]$Name, [string]$Source, [string]$Install, [string[]]$Extra) {
    $build = Join-Path $work $Name
    $args = @("-S",$Source,"-B",$build,"-G","Visual Studio 17 2022","-A","x64","-DCMAKE_INSTALL_PREFIX=$Install") + $Extra
    Invoke-Native "cmake" $args
    Invoke-Native "cmake" @("--build",$build,"--config","Release","--target","INSTALL")
}

function Get-PeDependencies([string]$RuntimeOut, [string]$Dumpbin) {
    $records = @()
    foreach ($binary in (Get-ChildItem -LiteralPath $RuntimeOut -File -Recurse | Where-Object Extension -in ".exe", ".dll")) {
        $lines = & $Dumpbin /DEPENDENTS $binary.FullName 2>&1
        if ($LASTEXITCODE -ne 0) { throw "dumpbin failed for $($binary.Name)" }
        $text = $lines -join "`n"
        $names = [regex]::Matches($text, '(?im)^\s+([A-Za-z0-9_.+-]+\.dll)\s*$') | ForEach-Object { $_.Groups[1].Value }
        foreach ($name in ($names | Sort-Object -Unique)) {
            $inBundle = Test-Path -LiteralPath (Join-Path $RuntimeOut $name)
            $msvcCrt = $name -match '^(concrt|msvcp|vcruntime|vcamp|vcomp)[0-9_]*\.dll$'
            $system = (Test-Path -LiteralPath (Join-Path (Join-Path $env:SystemRoot "System32") $name)) -and -not $msvcCrt
            $apiSet = $name -match '^(api|ext)-ms-win-'
            $records += [pscustomobject]@{ binary = $binary.Name; dependency = $name; bundled = $inBundle; windows_system = $system; api_set = $apiSet; msvc_crt = $msvcCrt }
        }
    }
    return $records
}

function Get-CrtDependencyNames([object[]]$Dependencies) {
    $names = @()
    foreach ($record in $Dependencies) {
        if ($null -eq $record) { throw "PE dependency record must not be null" }
        if ($record.PSObject.Properties.Name -notcontains "dependency") {
            throw "PE dependency record is missing its dependency property"
        }
        $name = [string]$record.dependency
        if ($name -match '^(concrt|msvcp|vcruntime|vcamp|vcomp)[0-9_]*\.dll$') { $names += $name }
    }
    return @($names | Sort-Object -Unique)
}

function Find-MsvcCrtRedist([string]$VisualStudioPath) {
    $redistRoot = Join-Path $VisualStudioPath "VC/Redist/MSVC"
    if (-not (Test-Path -LiteralPath $redistRoot)) { throw "MSVC redistributable root is missing: $redistRoot" }
    $crtCandidates = @(Get-ChildItem -LiteralPath $redistRoot -Directory -Recurse |
        Where-Object { $_.Name -eq "Microsoft.VC143.CRT" -and $_.FullName -match '[\\/]x64[\\/]Microsoft\.VC143\.CRT$' -and $_.Parent.Parent.Name -match '^\d+(\.\d+){1,3}$' } |
        Sort-Object { [version]$_.Parent.Parent.Name } -Descending)
    if ($crtCandidates.Count -eq 0) {
        $versions = @(Get-ChildItem -LiteralPath $redistRoot -Directory | Select-Object -ExpandProperty Name)
        throw "No x64 Microsoft.VC143.CRT directory exists under $redistRoot; versions=$($versions -join ', ')"
    }
    $crtFolder = $crtCandidates[0]
    $versionPath = Split-Path (Split-Path $crtFolder.FullName -Parent) -Parent
    $redistVersion = Get-Item -LiteralPath $versionPath
    $redistNoticeCandidates = @(Get-ChildItem -LiteralPath $redistVersion.FullName -Filter "redist.txt" -File -Recurse | Sort-Object FullName)
    if ($redistNoticeCandidates.Count -eq 0) {
        $redistNoticeCandidates = @(Get-ChildItem -LiteralPath $redistRoot -Filter "redist.txt" -File -Recurse | Sort-Object FullName)
    }
    $redistNotice = $null
    if ($redistNoticeCandidates.Count -gt 0) { $redistNotice = $redistNoticeCandidates[0].FullName }
    return [pscustomobject]@{
        redist_root = $redistRoot
        version = $redistVersion
        crt_folder = $crtFolder.FullName
        redist_notice = $redistNotice
    }
}

function Resolve-PeDependencies([string]$RuntimeOut, [string]$OutputRoot) {
    $installer = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio/Installer/vswhere.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw "VS where.exe is unavailable; cannot inspect PE dependencies or locate licensed CRT redist" }
    $vsInstall = (& $installer -latest -products '*' -property installationPath | Select-Object -First 1).Trim()
    if (-not $vsInstall) { throw "No Visual Studio installation was found for PE dependency inspection" }
    $toolsRoot = Join-Path $vsInstall "VC/Tools/MSVC"
    $toolsVersion = Get-ChildItem -LiteralPath $toolsRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $toolsVersion) { throw "No MSVC tools directory was found" }
    $dumpbin = Join-Path $toolsVersion.FullName "bin/Hostx64/x64/dumpbin.exe"
    if (-not (Test-Path -LiteralPath $dumpbin)) { throw "dumpbin was not found at the selected MSVC tool path" }

    $unexpectedCrtFiles = @(Get-ChildItem -LiteralPath $RuntimeOut -File -Recurse | Where-Object { $_.Name -match '^(concrt|msvcp|vcruntime|vcamp|vcomp)[0-9_]*\.dll$' })
    if ($unexpectedCrtFiles.Count -gt 0) {
        throw "Probe artifact must not contain Microsoft CRT DLLs: $($unexpectedCrtFiles.Name -join ', ')"
    }

    $dependencies = @(Get-PeDependencies $RuntimeOut $dumpbin)
    $missing = @($dependencies | Where-Object { -not $_.bundled -and -not $_.windows_system -and -not $_.api_set })
    $crtMissing = @(Get-CrtDependencyNames -Dependencies $missing)
    $redistVersion = $null
    $signedCrtFiles = @()
    if ($crtMissing.Count -gt 0) {
        $redist = Find-MsvcCrtRedist $vsInstall
        $redistVersion = $redist.version
        $crtFolder = $redist.crt_folder
        $redistNotice = $redist.redist_notice
        $eulaUrl = "https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx"
        $eulaPath = Join-Path $env:RUNNER_TEMP "Microsoft-Visual-C-Runtime-2015-2022-License.docx"
        Invoke-WebRequest -Uri $eulaUrl -OutFile $eulaPath
        if (-not (Test-Path -LiteralPath $eulaPath) -or (Get-Item -LiteralPath $eulaPath).Length -lt 10000) {
            throw "Microsoft Visual C++ Runtime 2015-2022 license terms could not be retrieved"
        }
        $eulaHash = (Get-FileHash -LiteralPath $eulaPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $noticeDir = Join-Path $OutputRoot "licenses/msvc-redist"
        New-Item -ItemType Directory -Path $noticeDir -Force | Out-Null
        $redistNoticeHash = $null
        if ($redistNotice) {
            Copy-Item -LiteralPath $redistNotice -Destination (Join-Path $noticeDir "redist.txt") -Force
            $redistNoticeHash = (Get-FileHash -LiteralPath $redistNotice -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $redistributionListUrl = "https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution"
        $redistributionListPath = Join-Path $env:RUNNER_TEMP "visual-studio-2022-redistribution.html"
        Invoke-WebRequest -Uri $redistributionListUrl -OutFile $redistributionListPath
        if ((Get-Item -LiteralPath $redistributionListPath).Length -lt 10000) {
            throw "Microsoft Visual Studio 2022 redistribution list snapshot is unexpectedly small"
        }
        $redistributionListHash = (Get-FileHash -LiteralPath $redistributionListPath -Algorithm SHA256).Hash.ToLowerInvariant()
        foreach ($crtDll in (Get-ChildItem -LiteralPath $crtFolder -Filter "*.dll" -File)) {
            $signature = Get-AuthenticodeSignature -LiteralPath $crtDll.FullName
            $signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
            $microsoftSigner = $signer -match '(?i)(?:^|,\s*)(?:CN|O)=Microsoft Corporation(?:,|$)'
            if ($signature.Status -ne "Valid" -or -not $microsoftSigner) {
                throw "MSVC CRT DLL lacks a valid Microsoft Authenticode signature: $($crtDll.Name) ($($signature.Status)); signer=$signer"
            }
            $signedCrtFiles += [pscustomobject]@{
                name = $crtDll.Name
                bytes = $crtDll.Length
                file_version = [Diagnostics.FileVersionInfo]::GetVersionInfo($crtDll.FullName).FileVersion
                sha256 = (Get-FileHash -LiteralPath $crtDll.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                signature_status = $signature.Status.ToString()
                signer = $signer
                signer_thumbprint = $signature.SignerCertificate.Thumbprint
            }
        }
        if ($signedCrtFiles.Count -eq 0) { throw "The selected MSVC CRT redistributable directory contains no DLLs" }
        $availableCrtNames = @($signedCrtFiles | ForEach-Object { $_.name })
        $unavailableCrtNames = @($crtMissing | Where-Object { $availableCrtNames -notcontains $_ })
        if ($unavailableCrtNames.Count -gt 0) {
            throw "Runner MSVC redist $($redistVersion.Name) lacks imported CRT DLLs: $($unavailableCrtNames -join ', ')"
        }
        $script:RunnerMsvcCrtPath = $crtFolder
        # The runner-provided CRT is used only for this smoke test. It is never
        # copied into the public artifact; standalone redistribution rights
        # require a separate publisher-license review.
        $missing = @($missing | Where-Object { $crtMissing -notcontains $_.dependency })
        $msvcLicenseEvidence = [ordered]@{
            product = "Microsoft Visual C++ Runtime 2015-2022"
            visual_studio_redist_version = $redistVersion.Name
            source_directory = $crtFolder
            included_in_probe_artifact = $false
            redist_txt_present_in_installation = [bool]$redistNotice
            redist_txt_sha256 = $redistNoticeHash
            license_terms_url = $eulaUrl
            license_terms_sha256 = $eulaHash
            visual_studio_2022_redistribution_list_url = $redistributionListUrl
            visual_studio_2022_redistribution_list_snapshot_sha256 = $redistributionListHash
            visual_c_redistribution_guidance = "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files"
            signed_dlls = $signedCrtFiles
            note = "Microsoft REDIST.txt is the distributable list referenced by the applicable Visual Studio license terms; it is not itself the license. These files are Microsoft redistributables, not MIT/GPL components."
        }
        $msvcLicenseEvidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $noticeDir "msvc-redist-evidence.json") -Encoding UTF8
        $dependencies = @(Get-PeDependencies $RuntimeOut $dumpbin)
        $missing = @($dependencies | Where-Object {
            $runnerCrtAvailable = $false
            if ($script:RunnerMsvcCrtPath -and ($availableCrtNames -contains $_.dependency)) {
                $runnerCrtAvailable = $true
            }
            -not $_.bundled -and -not $_.windows_system -and -not $_.api_set -and -not $runnerCrtAvailable
        })
    }
    if ($missing.Count -gt 0) {
        $names = ($missing | ForEach-Object { "$($_.binary):$($_.dependency)" }) -join ", "
        throw "Runtime has unresolved non-system PE imports: $names"
    }
    $redistFiles = @()
    if ($crtMissing.Count -gt 0) {
        $redistFiles = $signedCrtFiles
    }
    $redistVersionName = $null
    if ($redistVersion) { $redistVersionName = $redistVersion.Name }
    $standaloneReview = "not required by imports"
    if ($crtMissing.Count -gt 0) { $standaloneReview = "required; not established by this runner test" }
    $report = [ordered]@{
        dumpbin = $dumpbin.Substring($vsInstall.Length + 1).Replace("\", "/")
        visual_studio_redist_version = $redistVersionName
        msvc_redist_included = $false
        runner_msvc_redist_used_for_smoke = ($crtMissing.Count -gt 0)
        runner_msvc_redist_version = $redistVersionName
        runner_msvc_redist_directory = $script:RunnerMsvcCrtPath
        standalone_distribution_review = $standaloneReview
        dependencies = $dependencies
        msvc_redist_files = $redistFiles
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot "runtime-dependency-report.json") -Encoding UTF8
    $dependencySummary = @($dependencies | ForEach-Object { "$($_.binary):$($_.dependency)" }) -join "; "
    Write-Output "PE imports verified for this runner smoke; msvc_crt_bundled=false; runner_redist=$redistVersionName; dependencies=$dependencySummary"
}

if ($Mode -eq "DiscoverOrt") {
    $item = $runtime.sources | Where-Object name -eq "onnxruntime"
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $zip = Join-Path $work "onnxruntime-win-x64-1.14.1.zip"
    Invoke-WebRequest -Uri $item.windows_binary_url -OutFile $zip
    $evidence = [ordered]@{
        url = $item.windows_binary_url
        bytes = (Get-Item -LiteralPath $zip).Length
        sha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        upstream_digest = $null
        source_commit = $item.commit
        review = "Observed over HTTPS; human review required before the value is copied into the lock."
    }
    $evidenceJson = $evidence | ConvertTo-Json -Depth 5 -Compress
    $evidenceJson | Set-Content -LiteralPath (Join-Path $OutputRoot "ort-hash-evidence.json") -Encoding UTF8
    Write-Output $evidenceJson
    Write-Output "Digest evidence written; this mode does not build or trust the asset."
    exit 0
}

if ($Mode -eq "TestPeDependencyRecords") {
    $single = [object[]]@([pscustomobject]@{ binary = "piper.exe"; dependency = "VCRUNTIME140.dll"; bundled = $false; windows_system = $false; api_set = $false; msvc_crt = $true })
    $multiple = [object[]]@(
        [pscustomobject]@{ binary = "piper.exe"; dependency = "VCRUNTIME140.dll"; bundled = $false; windows_system = $false; api_set = $false; msvc_crt = $true },
        [pscustomobject]@{ binary = "piper-phonemize.dll"; dependency = "MSVCP140.dll"; bundled = $false; windows_system = $false; api_set = $false; msvc_crt = $true },
        [pscustomobject]@{ binary = "piper.exe"; dependency = "KERNEL32.dll"; bundled = $false; windows_system = $true; api_set = $false; msvc_crt = $false }
    )
    $empty = [object[]]@()
    $singleNames = @(Get-CrtDependencyNames -Dependencies $single)
    $multipleNames = @(Get-CrtDependencyNames -Dependencies $multiple)
    $emptyNames = @(Get-CrtDependencyNames -Dependencies $empty)
    if ($singleNames.Count -ne 1 -or $singleNames[0] -ne "VCRUNTIME140.dll") { throw "Single PE record fixture failed" }
    if ($multipleNames.Count -ne 2 -or $multipleNames -notcontains "VCRUNTIME140.dll" -or $multipleNames -notcontains "MSVCP140.dll") { throw "Multiple PE record fixture failed" }
    if ($emptyNames.Count -ne 0) { throw "Empty PE record fixture failed" }
    $json = [ordered]@{ dependencies = @($multiple); msvc_crt_missing = $multipleNames } | ConvertTo-Json -Depth 6 -Compress
    $roundTrip = $json | ConvertFrom-Json
    if ($roundTrip.dependencies.Count -ne 3 -or $roundTrip.msvc_crt_missing.Count -ne 2) { throw "PE dependency JSON fixture failed" }
    Write-Output "PE dependency record fixtures passed: single, multiple, empty, and JSON round-trip."
    exit 0
}

if ($Mode -eq "TestMsvcRedistDiscovery") {
    $installer = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio/Installer/vswhere.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw "VS where.exe is unavailable" }
    $vsInstall = (& $installer -latest -products '*' -property installationPath | Select-Object -First 1).Trim()
    if (-not $vsInstall) { throw "No Visual Studio installation was found" }
    $redist = Find-MsvcCrtRedist $vsInstall
        $noticeState = if ($redist.redist_notice) { $redist.redist_notice } else { "not-installed; use the official Microsoft redistribution-list source" }
        Write-Output "MSVC CRT discovery passed; visual_studio=$vsInstall; redist_version=$($redist.version.Name); crt_folder=$($redist.crt_folder); redist_txt=$noticeState"
    foreach ($crtDll in (Get-ChildItem -LiteralPath $redist.crt_folder -Filter "*.dll" -File)) {
        $signature = Get-AuthenticodeSignature -LiteralPath $crtDll.FullName
        $signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
        $fileVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($crtDll.FullName).FileVersion
        $hash = (Get-FileHash -LiteralPath $crtDll.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Output "CRT signer probe: name=$($crtDll.Name); version=$fileVersion; signature=$($signature.Status); signer=$signer; sha256=$hash"
    }
    exit 0
}

if ($Mode -eq "SourceArchive") {
    New-Item -ItemType Directory -Path $SourceRoot,$work,$OutputRoot -Force | Out-Null
    foreach ($dependency in $runtime.sources) { [void](Get-Source $dependency.name) }
    $sourceArchive = Join-Path $OutputRoot "piper-runtime-source.zip"
    Invoke-Native "powershell" @("-NoProfile","-File",(Join-Path $PSScriptRoot "archive_piper_sources.ps1"),
        "-LockPath",$LockPath,"-SourceRoot",$SourceRoot,"-OutputZip",$sourceArchive)
    Invoke-Native "python" @("scripts/verify_piper_source_archive.py","--archive",$sourceArchive,"--lock",$LockPath)
    Write-Output "All six pinned source commits were archived and verified; model weights are excluded."
    exit 0
}

$ortItem = $runtime.sources | Where-Object name -eq "onnxruntime"
if (-not $ortItem.windows_binary_sha256 -or $ortItem.windows_binary_sha256 -notmatch "^[a-f0-9]{64}$") {
    throw "ORT SHA-256 review gate is unset. Run DiscoverOrt, review it, update the lock, then rerun."
}
New-Item -ItemType Directory -Path $SourceRoot,$work,$OutputRoot -Force | Out-Null
$piper = Get-Source "piper"
$phonemize = Get-Source "piper-phonemize"
$espeak = Get-Source "espeak-ng"
$fmt = Get-Source "fmt"
$spdlog = Get-Source "spdlog"
[void](Get-Source "onnxruntime") # Corresponding source for the pinned runtime binary and its license bundle.

$ortZip = Join-Path $work "onnxruntime-win-x64-1.14.1.zip"
Invoke-WebRequest -Uri $ortItem.windows_binary_url -OutFile $ortZip
$actualHash = (Get-FileHash -LiteralPath $ortZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $ortItem.windows_binary_sha256) { throw "ORT SHA-256 mismatch: $actualHash" }
$ortRoot = Join-Path $work "onnxruntime-win-x64-1.14.1"
Expand-Archive -LiteralPath $ortZip -DestinationPath $work -Force
if (-not (Test-Path -LiteralPath (Join-Path $ortRoot "include/onnxruntime_c_api.h"))) { throw "Unexpected ORT archive layout" }

$install = Join-Path $work "install"
$fmtInstall = Join-Path $install "fmt"
$spdlogInstall = Join-Path $install "spdlog"
$espeakInstall = Join-Path $install "espeak-ng"
$phonemizeInstall = Join-Path $install "piper-phonemize"
$piperInstall = Join-Path $install "piper"
Build-CMake "fmt" $fmt $fmtInstall @("-DFMT_DOC=OFF","-DFMT_TEST=OFF","-DBUILD_SHARED_LIBS=OFF")
Build-CMake "spdlog" $spdlog $spdlogInstall @("-DSPDLOG_BUILD_SHARED=OFF","-DSPDLOG_INSTALL=ON","-DSPDLOG_FMT_EXTERNAL=ON","-Dfmt_DIR=$(Join-Path $fmtInstall 'lib/cmake/fmt')")
Build-CMake "espeak-ng" $espeak $espeakInstall @("-DBUILD_SHARED_LIBS=ON","-DUSE_ASYNC=OFF","-DUSE_MBROLA=OFF","-DUSE_LIBSONIC=OFF","-DUSE_LIBPCAUDIO=OFF","-DUSE_KLATT=OFF","-DUSE_SPEECHPLAYER=OFF")
Build-CMake "piper-phonemize" $phonemize $phonemizeInstall @("-DESPEAK_NG_DIR=$espeakInstall","-DONNXRUNTIME_DIR=$ortRoot")
$piperCompileHook = Join-Path $work "piper-spdlog-compile-definition.cmake"
Set-Content -LiteralPath $piperCompileHook -Value "add_compile_definitions(SPDLOG_FMT_EXTERNAL)" -Encoding ASCII
Build-CMake "piper" $piper $piperInstall @("-DFMT_DIR=$fmtInstall","-DSPDLOG_DIR=$spdlogInstall","-DPIPER_PHONEMIZE_DIR=$phonemizeInstall","-DCMAKE_PROJECT_INCLUDE=$piperCompileHook")
$piperProject = Get-Content -LiteralPath (Join-Path $work "piper/piper.vcxproj") -Raw
if ($piperProject -notmatch "SPDLOG_FMT_EXTERNAL") { throw "Piper project is missing the external fmt compile definition" }
if ($piperProject -notmatch "<WarningLevel>Level3</WarningLevel>" -or $piperProject -notmatch "<ExceptionHandling>Sync</ExceptionHandling>") {
    throw "Piper project did not retain the normal MSVC warning and C++ exception settings"
}
Write-Output "Piper project retained MSVC warning/exception defaults and added SPDLOG_FMT_EXTERNAL via CMake hook."

$runtimeOut = Join-Path $OutputRoot "speech/runtime/piper"
New-Item -ItemType Directory -Path $runtimeOut,(Join-Path $OutputRoot "licenses/onnxruntime") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $piperInstall "piper.exe") -Destination $runtimeOut
Get-ChildItem -LiteralPath $piperInstall -Filter "*.dll" -File -Recurse | Copy-Item -Destination $runtimeOut
Get-ChildItem -LiteralPath (Join-Path $ortRoot "lib") -Filter "*.dll" -File | Copy-Item -Destination $runtimeOut -Force
Copy-Item -LiteralPath (Join-Path $piperInstall "espeak-ng-data") -Destination $runtimeOut -Recurse
Resolve-PeDependencies $runtimeOut $OutputRoot
$oldPath = $env:PATH
try {
    $env:PATH = "$runtimeOut;$script:RunnerMsvcCrtPath;$env:SystemRoot\System32;$env:SystemRoot"
    Invoke-Native (Join-Path $runtimeOut "piper.exe") @("--version")
} finally { $env:PATH = $oldPath }
Copy-Item -LiteralPath (Join-Path $ortRoot "LICENSE") -Destination (Join-Path $OutputRoot "licenses/onnxruntime/LICENSE")
Copy-Item -LiteralPath (Join-Path $ortRoot "ThirdPartyNotices.txt") -Destination (Join-Path $OutputRoot "licenses/onnxruntime/ThirdPartyNotices.txt")

$files = Get-ChildItem -LiteralPath $runtimeOut -File -Recurse | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($OutputRoot.Length + 1).Replace("\","/")
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
[ordered]@{ files = @($files); profile = $lock.profile } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot "runtime-manifest.json") -Encoding UTF8

if ($Mode -eq "VoiceSmoke") {
    foreach ($model in $lock.models) {
        if ($model.license_evidence.status -ne "CI_TEST_LICENSE_REVIEWED") {
            throw "Pinned model-license CI test gate is unset for $($model.accent)"
        }
    }
    $modelRoot = Join-Path $env:RUNNER_TEMP "woer-piper-voice-input"
    Invoke-Native "python" @("scripts/fetch_pinned_voices.py","--lock",$LockPath,"--dest",$modelRoot)
    $env:WOER_TEST_CRT_PATH = $script:RunnerMsvcCrtPath
    Invoke-Native "python" @("scripts/voice_runtime_smoke.py","--runtime",$runtimeOut,"--models",(Join-Path $modelRoot "speech/voices"),
        "--build-root",$OutputRoot,"--lock",$LockPath,"--report",(Join-Path $OutputRoot "voice-smoke.json"))
}

Invoke-Native "powershell" @("-NoProfile","-File",(Join-Path $PSScriptRoot "archive_piper_sources.ps1"),
    "-LockPath",$LockPath,"-SourceRoot",$SourceRoot,"-OutputZip",(Join-Path $OutputRoot "piper-runtime-source.zip"))
Invoke-Native "python" @("scripts/verify_piper_source_archive.py","--archive",(Join-Path $OutputRoot "piper-runtime-source.zip"),"--lock",$LockPath)
Write-Output "Build script reached the end only after all selected gates and commands succeeded."

