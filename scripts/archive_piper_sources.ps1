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

    $treeLines = @(& git -C $source ls-tree -r $dependency.commit)
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect gitlinks: $($dependency.name)" }
    $gitlinks = @()
    foreach ($line in $treeLines) {
        if ($line -match '^160000 commit ([0-9a-f]{40})\t(.+)$') {
            $gitlinks += [pscustomobject]@{ commit = $matches[1]; path = $matches[2] }
        }
    }
    $expectedSubmodules = @()
    if ($null -ne $dependency.submodules) { $expectedSubmodules = @($dependency.submodules) }
    $actualPaths = @($gitlinks | ForEach-Object { $_.path } | Sort-Object)
    $expectedPaths = @($expectedSubmodules | ForEach-Object { $_.path } | Sort-Object)
    if (($actualPaths -join "`n") -ne ($expectedPaths -join "`n")) {
        throw "Gitlink path set differs from lock for $($dependency.name): $($actualPaths -join '; ')"
    }
    $gitlinkRecords = @($gitlinks | ForEach-Object {
        $link = $_
        $pin = @($expectedSubmodules | Where-Object { $_.path -eq $link.path })
        if ($pin.Count -ne 1) { throw "Gitlink is not uniquely pinned: $($dependency.name)/$($link.path)" }
        [ordered]@{ path = $link.path; repository = $pin[0].repository; commit = $link.commit }
    })
    $submoduleRecords = @()
    foreach ($submodule in $expectedSubmodules) {
        $gitlink = $gitlinks | Where-Object { $_.path -eq $submodule.path } | Select-Object -First 1
        if (-not $gitlink -or $gitlink.commit -ne $submodule.commit) { throw "Gitlink commit mismatch: $($dependency.name)/$($submodule.path)" }
        $configKey = "submodule.$($submodule.path).url"
        $configuredUrl = (& git -C $source config -f .gitmodules --get $configKey).Trim()
        if ($LASTEXITCODE -ne 0 -or $configuredUrl -ne $submodule.repository) { throw "Gitlink URL mismatch: $($dependency.name)/$($submodule.path)" }
        & git -C $source submodule update --init --depth 1 -- $submodule.path
        if ($LASTEXITCODE -ne 0) { throw "Submodule fetch failed: $($submodule.path)" }
        $submoduleRoot = Join-Path $source $submodule.path
        $submoduleHead = (& git -C $submoduleRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $submoduleHead -ne $submodule.commit) { throw "Submodule checkout mismatch: $($submodule.path)" }
        $nestedLines = @(& git -C $submoduleRoot ls-tree -r $submodule.commit)
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect nested gitlinks: $($submodule.path)" }
        if (@($nestedLines | Where-Object { $_ -match '^160000 commit ' }).Count -gt 0) { throw "Unpinned nested gitlink: $($submodule.path)" }

        $leaf = ($submodule.path -split '/')[-1]
        $subArchiveDir = Join-Path $sourcesDir "onnxruntime-submodules"
        New-Item -ItemType Directory -Path $subArchiveDir -Force | Out-Null
        $subArchiveName = "$leaf-$($submodule.commit).zip"
        $subArchivePath = Join-Path $subArchiveDir $subArchiveName
        & git -C $submoduleRoot archive --format=zip --output=$subArchivePath $submodule.commit "." ":(exclude,glob)**/*.onnx" ":(exclude,glob)**/*.ort"
        if ($LASTEXITCODE -ne 0) { throw "Submodule source archive failed: $($submodule.path)" }

        $subNoticeDir = Join-Path $noticesDir "onnxruntime-$leaf"
        New-Item -ItemType Directory -Path $subNoticeDir -Force | Out-Null
        $subLicenseFiles = @(Get-ChildItem -LiteralPath $submoduleRoot -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE|ThirdPartyNotices)' })
        if ($subLicenseFiles.Count -eq 0) { throw "No top-level license/notice found for submodule: $($submodule.path)" }
        foreach ($licenseFile in $subLicenseFiles) { Copy-Item -LiteralPath $licenseFile.FullName -Destination $subNoticeDir }
        $subArchiveInfo = Get-Item -LiteralPath $subArchivePath
        $submoduleRecords += [ordered]@{
            path = $submodule.path
            repository = $submodule.repository
            commit = $submodule.commit
            archive = "sources/onnxruntime-submodules/$subArchiveName"
            bytes = $subArchiveInfo.Length
            sha256 = (Get-FileHash -LiteralPath $subArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
            gitlinks = @()
            notices = @($subLicenseFiles | ForEach-Object { "notices/onnxruntime-$leaf/$($_.Name)" })
            excluded_model_files = @("**/*.onnx", "**/*.ort")
        }
    }

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
        gitlinks = @($gitlinkRecords)
        archive = "sources/$archiveName"
        bytes = $archiveInfo.Length
        sha256 = $archiveHash
        notices = @($licenseFiles | ForEach-Object { "notices/$($dependency.name)/$($_.Name)" })
        excluded_model_files = @("**/*.onnx", "**/*.ort")
        submodules = @($submoduleRecords)
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
