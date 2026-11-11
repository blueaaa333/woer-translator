param(
    [string]$LockPath = (Join-Path $PSScriptRoot "voice_runtime_lock.json"),
    [string]$SourceRoot = (Join-Path $env:RUNNER_TEMP "woer-piper-source"),
    [string]$OutputZip = (Join-Path $env:GITHUB_WORKSPACE "build/voice-runtime/piper-runtime-source.zip")
)
$ErrorActionPreference = "Stop"
$lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$stage = Join-Path $env:RUNNER_TEMP "woer-piper-source-archive"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $stage "sources"),(Join-Path $stage "notices") -Force | Out-Null
foreach ($dependency in $lock.runtime.sources) {
    if ($dependency.name -eq "onnxruntime") { continue }
    $source = Join-Path $SourceRoot $dependency.name
    $actual = (& git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $dependency.commit) { throw "Non-pinned source: $($dependency.name)" }
    $archive = Join-Path $stage "sources/$($dependency.name)-$($dependency.commit).zip"
    & git -C $source archive --format=zip --output=$archive $dependency.commit
    if ($LASTEXITCODE -ne 0) { throw "Source archive failed: $($dependency.name)" }
    Get-ChildItem -Path $source -File -Include "LICENSE*","COPYING*" | Copy-Item -Destination (Join-Path $stage "notices")
}
Copy-Item -LiteralPath $LockPath -Destination (Join-Path $stage "voice_runtime_lock.json")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "build_piper_runtime.ps1") -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "archive_piper_sources.ps1") -Destination $stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README-runtime-source.md") -Destination $stage
if (Test-Path -LiteralPath $OutputZip) { Remove-Item -LiteralPath $OutputZip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $OutputZip -CompressionLevel Optimal
