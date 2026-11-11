param(
    [ValidateSet("DiscoverOrt", "SourceArchive", "BuildRuntime", "VoiceSmoke")]
    [string]$Mode = "DiscoverOrt",
    [string]$LockPath = (Join-Path $PSScriptRoot "voice_runtime_lock.json"),
    [string]$SourceRoot = (Join-Path $env:RUNNER_TEMP "woer-piper-source"),
    [string]$OutputRoot = (Join-Path $env:GITHUB_WORKSPACE "build/voice-runtime")
)

$ErrorActionPreference = "Stop"
$lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$runtime = $lock.runtime
$work = Join-Path $env:RUNNER_TEMP "woer-piper-build"

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
            $system = Test-Path -LiteralPath (Join-Path (Join-Path $env:SystemRoot "System32") $name)
            $apiSet = $name -match '^(api|ext)-ms-win-'
            $records += [ordered]@{ binary = $binary.Name; dependency = $name; bundled = $inBundle; windows_system = $system -or $apiSet }
        }
    }
    return $records
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

    $dependencies = @(Get-PeDependencies $RuntimeOut $dumpbin)
    $missing = @($dependencies | Where-Object { -not $_.bundled -and -not $_.windows_system })
    $crtMissing = @($missing | Where-Object { $_.dependency -match '^(concrt|msvcp|vcruntime|vcamp|vcomp)[0-9_]*\.dll$' } | Select-Object -ExpandProperty dependency -Unique)
    $redistVersion = $null
    if ($crtMissing.Count -gt 0) {
        $redistRoot = Join-Path $vsInstall "VC/Redist/MSVC"
        $redistVersion = Get-ChildItem -LiteralPath $redistRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if (-not $redistVersion) { throw "MSVC CRT is imported but no Visual C++ redistributable was found" }
        $crtFolder = Join-Path $redistVersion.FullName "x64/Microsoft.VC143.CRT"
        $redistNotice = Join-Path $redistVersion.FullName "redist.txt"
        if (-not (Test-Path -LiteralPath $crtFolder) -or -not (Test-Path -LiteralPath $redistNotice)) {
            throw "MSVC CRT redist or its redist.txt notice is missing"
        }
        Get-ChildItem -LiteralPath $crtFolder -File | Copy-Item -Destination $RuntimeOut -Force
        $noticeDir = Join-Path $OutputRoot "licenses/msvc-redist"
        New-Item -ItemType Directory -Path $noticeDir -Force | Out-Null
        Copy-Item -LiteralPath $redistNotice -Destination (Join-Path $noticeDir "redist.txt") -Force
        $dependencies = @(Get-PeDependencies $RuntimeOut $dumpbin)
        $missing = @($dependencies | Where-Object { -not $_.bundled -and -not $_.windows_system })
    }
    if ($missing.Count -gt 0) {
        $names = ($missing | ForEach-Object { "$($_.binary):$($_.dependency)" }) -join ", "
        throw "Runtime has unresolved non-system PE imports: $names"
    }
    $redistFiles = @()
    if ($crtMissing.Count -gt 0) {
        $redistFiles = @(Get-ChildItem -LiteralPath (Join-Path $redistVersion.FullName "x64/Microsoft.VC143.CRT") -File | ForEach-Object {
            [ordered]@{ name = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
        })
    }
    $redistVersionName = $null
    if ($redistVersion) { $redistVersionName = $redistVersion.Name }
    $report = [ordered]@{
        dumpbin = $dumpbin.Substring($vsInstall.Length + 1).Replace("\", "/")
        visual_studio_redist_version = $redistVersionName
        msvc_redist_included = ($crtMissing.Count -gt 0)
        dependencies = $dependencies
        msvc_redist_files = $redistFiles
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot "runtime-dependency-report.json") -Encoding UTF8
    $dependencySummary = @($dependencies | ForEach-Object { "$($_.binary):$($_.dependency)" }) -join "; "
    Write-Output "PE dependency closure passed; msvc_redist=$($crtMissing.Count -gt 0); dependencies=$dependencySummary"
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
New-Item -ItemType Directory -Path $SourceRoot,$work,$OutputRoot | Out-Null
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

$runtimeOut = Join-Path $OutputRoot "speech/runtime/piper"
New-Item -ItemType Directory -Path $runtimeOut,(Join-Path $OutputRoot "licenses/onnxruntime") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $piperInstall "piper.exe") -Destination $runtimeOut
Get-ChildItem -LiteralPath $piperInstall -Filter "*.dll" -File -Recurse | Copy-Item -Destination $runtimeOut
Get-ChildItem -LiteralPath (Join-Path $ortRoot "lib") -Filter "*.dll" -File | Copy-Item -Destination $runtimeOut -Force
Copy-Item -LiteralPath (Join-Path $piperInstall "espeak-ng-data") -Destination $runtimeOut -Recurse
Resolve-PeDependencies $runtimeOut $OutputRoot
$oldPath = $env:PATH
try {
    $env:PATH = "$runtimeOut;$env:SystemRoot\System32;$env:SystemRoot"
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
    Invoke-Native "python" @("scripts/voice_runtime_smoke.py","--runtime",$runtimeOut,"--models",(Join-Path $modelRoot "speech/voices"),
        "--build-root",$OutputRoot,"--lock",$LockPath,"--report",(Join-Path $OutputRoot "voice-smoke.json"))
}

Invoke-Native "powershell" @("-NoProfile","-File",(Join-Path $PSScriptRoot "archive_piper_sources.ps1"),
    "-LockPath",$LockPath,"-SourceRoot",$SourceRoot,"-OutputZip",(Join-Path $OutputRoot "piper-runtime-source.zip"))
Invoke-Native "python" @("scripts/verify_piper_source_archive.py","--archive",(Join-Path $OutputRoot "piper-runtime-source.zip"),"--lock",$LockPath)
Write-Output "Build script reached the end only after all selected gates and commands succeeded."
