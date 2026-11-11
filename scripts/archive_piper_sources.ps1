param(
    [string]$LockPath = (Join-Path $PSScriptRoot "voice_runtime_lock.json"),
    [string]$SourceRoot = (Join-Path $env:RUNNER_TEMP "woer-piper-source"),
    [string]$OutputZip = (Join-Path $env:GITHUB_WORKSPACE "build/voice-runtime/piper-runtime-source.zip")
)
$ErrorActionPreference = "Stop"
$lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$stage = Join-Path $env:RUNNER_TEMP "woer-piper-source-archive"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
$sourcesDir = Join-Path $stage "sources"
$noticesDir = Join-Path $stage "notices"
New-Item -ItemType Directory -Path $sourcesDir,$noticesDir -Force | Out-Null
$sourceRecords = @()

foreach ($dependency in $lock.runtime.sources) {
    $source = Join-Path $SourceRoot $dependency.name
    $actual = (& git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $dependency.commit) { throw "Non-pinned source: $($dependency.name)" }

    $gitlinks = @(& git -C $source ls-tree -r $dependency.commit | Where-Object { $_ -match '^160000 commit ' })
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect gitlinks: $($dependency.name)" }
    if ($gitlinks.Count -gt 0) { throw "Lock has no nested commit pins for $($dependency.name): $($gitlinks -join '; ')" }

    $archiveName = "$($dependency.name)-$($dependency.commit).zip"
    $archivePath = Join-Path $sourcesDir $archiveName
    & git -C $source archive --format=zip --output=$archivePath $dependency.commit "." ":(exclude,glob)**/*.onnx" ":(exclude,glob)**/*.ort"
    if ($LASTEXITCODE -ne 0) { throw "Source archive failed: $($dependency.name)" }

    $componentNotices = Join-Path $noticesDir $dependency.name
    New-Item -ItemType Directory -Path $componentNotices -Force | Out-Null
    $licenseFiles = @(Get-ChildItem -LiteralPath $source -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE|ThirdPartyNotices)' })
    if ($licenseFiles.Count -eq 0) { throw "No top-level license/notice found: $($dependency.name)" }
    foreach ($licenseFile in $licenseFiles) { Copy-Item -LiteralPath $licenseFile.FullName -Destination $componentNotices }
    if ($dependency.name -eq "onnxruntime") {
        foreach ($required in @("LICENSE", "ThirdPartyNotices.txt")) {
            if (-not (Test-Path -LiteralPath (Join-Path $componentNotices $required))) { throw "Missing ORT notice: $required" }
        }
    }

    $archiveInfo = Get-Item -LiteralPath $archivePath
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceRecords += [ordered]@{
        name = $dependency.name
        repository = $dependency.repository
        commit = $dependency.commit
        gitlinks = @()
        archive = "sources/$archiveName"
        bytes = $archiveInfo.Length
        sha256 = $archiveHash
        notices = @($licenseFiles | ForEach-Object { "notices/$($dependency.name)/$($_.Name)" })
        excluded_model_files = @("**/*.onnx", "**/*.ort")
    }
}

Copy-Item -LiteralPath $LockPath -Destination (Join-Path $stage "voice_runtime_lock.json")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "build_piper_runtime.ps1") -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "archive_piper_sources.ps1") -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "verify_piper_source_archive.py") -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README-runtime-source.md") -Destination $stage
$manifestPath = Join-Path $stage "source-manifest.json"
[ordered]@{ schema = 1; profile = $lock.profile; sources = @($sourceRecords) } |
    ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

if (Test-Path -LiteralPath $OutputZip) { Remove-Item -LiteralPath $OutputZip -Force }
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputZip) -Force | Out-Null
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $OutputZip -CompressionLevel Optimal
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path (Split-Path -Parent $OutputZip) "source-manifest.json")
Write-Output "Archived $($sourceRecords.Count) pinned source commits; ONNX/ORT model files were excluded."
