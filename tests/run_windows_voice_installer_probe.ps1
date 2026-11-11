param(
    [Parameter(Mandatory=$true)][string]$CandidateSetup,
    [Parameter(Mandatory=$false)][string]$ReportRoot = "build/voice-package-review"
)
$ErrorActionPreference = "Stop"

$runnerTemp = [IO.Path]::GetFullPath($env:RUNNER_TEMP)
$testRoot = [IO.Path]::GetFullPath((Join-Path $runnerTemp "woer-voice-installer-probe"))
if (-not $testRoot.StartsWith($runnerTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Probe root is outside RUNNER_TEMP: $testRoot"
}
$resolvedSetup = [IO.Path]::GetFullPath($CandidateSetup)
$resolvedReportRoot = [IO.Path]::GetFullPath($ReportRoot)
New-Item -ItemType Directory -Path $testRoot,$resolvedReportRoot -Force | Out-Null

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CrtRecords([string]$Root) {
    $names = @("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")
    $records = @()
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $records }
    foreach ($name in $names) {
        foreach ($file in @(Get-ChildItem -LiteralPath $Root -Filter $name -File -Recurse -ErrorAction SilentlyContinue)) {
            $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
            $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
            $records += [ordered]@{
                name = $file.Name
                path = $file.FullName
                bytes = $file.Length
                sha256 = Get-Sha256 $file.FullName
                file_version = [Diagnostics.FileVersionInfo]::GetVersionInfo($file.FullName).FileVersion
                signature_status = [string]$signature.Status
                signer = $subject
            }
        }
    }
    return $records
}

function Get-TreeDigest([string]$Root) {
    $rootPath = [IO.Path]::GetFullPath($Root)
    $builder = [Text.StringBuilder]::new()
    $entries = @(Get-ChildItem -LiteralPath $rootPath -File -Recurse -Force | Sort-Object FullName)
    foreach ($entry in $entries) {
        $relative = $entry.FullName.Substring($rootPath.Length + 1).Replace("\", "/")
        [void]$builder.Append($relative).Append("|").Append($entry.Length).Append("|").Append((Get-Sha256 $entry.FullName)).Append("`n")
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes($builder.ToString())
    $sha = [Security.Cryptography.SHA256]::HashData($bytes)
    return [Convert]::ToHexString($sha).ToLowerInvariant()
}

function Set-InstallTreeAccess([string]$Root, [string]$Mode) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $paths = @(Get-ChildItem -LiteralPath $Root -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending)
    $paths += Get-Item -LiteralPath $Root -Force
    foreach ($entry in $paths) {
        $acl = Get-Acl -LiteralPath $entry.FullName
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($existing in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($existing) }
        if ($Mode -eq "ReadOnly" -and $entry.PSIsContainer) {
            $rights = [Security.AccessControl.FileSystemRights]::ReadAndExecute
            $inheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
        } elseif ($Mode -eq "ReadOnly") {
            $rights = [Security.AccessControl.FileSystemRights]::ReadAndExecute
            $inheritance = [Security.AccessControl.InheritanceFlags]::None
        } elseif ($entry.PSIsContainer) {
            $rights = [Security.AccessControl.FileSystemRights]::FullControl
            $inheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
        } else {
            $rights = [Security.AccessControl.FileSystemRights]::FullControl
            $inheritance = [Security.AccessControl.InheritanceFlags]::None
        }
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $identity, $rights, $inheritance, [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $entry.FullName -AclObject $acl
    }
}

function Get-AclRecord([string]$Path) {
    $acl = Get-Acl -LiteralPath $Path
    return [ordered]@{
        path = $Path
        protected = $acl.AreAccessRulesProtected
        rules = @($acl.Access | ForEach-Object {
            [ordered]@{ identity = $_.IdentityReference.Value; rights = [string]$_.FileSystemRights;
                type = [string]$_.AccessControlType; inherited = $_.IsInherited }
        })
    }
}

function Assert-ReadOnly([string]$Root) {
    $model = Join-Path $Root "_internal\speech\voices\uk\dictionary-voice.onnx"
    if (-not (Test-Path -LiteralPath $model)) { $model = Get-ChildItem -LiteralPath $Root -Filter "dictionary-voice.onnx" -File -Recurse | Select-Object -First 1 -ExpandProperty FullName }
    if (-not $model) { throw "Bundled UK model is missing from installed tree" }
    $rootWriteDenied = $false
    try { [IO.File]::WriteAllText((Join-Path $Root ".write-probe"), "x") }
    catch [UnauthorizedAccessException] { $rootWriteDenied = $true }
    if (-not $rootWriteDenied) { throw "Installed application directory accepted a write" }
    $modelWriteDenied = $false
    try {
        $stream = [IO.File]::Open($model, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::Read)
        $stream.Dispose()
    } catch [UnauthorizedAccessException] { $modelWriteDenied = $true }
    if (-not $modelWriteDenied) { throw "Installed voice model accepted write access" }
    return [ordered]@{ root_write_denied = $rootWriteDenied; model_write_denied = $modelWriteDenied; model = $model }
}

function Invoke-AppVoiceSmoke([string]$Exe, [string]$LocalData, [string]$Label) {
    $report = Join-Path $resolvedReportRoot "$Label-voice-smoke.json"
    $marker = Join-Path $testRoot "$Label-smoke-inspected.marker"
    if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report -Force }
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
    $pathWithoutVs = ($env:PATH -split ';' | Where-Object { $_ -notmatch '(?i)\\Microsoft Visual Studio\\|\\VC\\Tools\\MSVC\\' }) -join ';'
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Exe
    $start.WorkingDirectory = $testRoot
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.ArgumentList.Add('--offline-voice-self-test')
    $start.ArgumentList.Add($report)
    $start.ArgumentList.Add('--voice-probe-release')
    $start.ArgumentList.Add($marker)
    $start.Environment['LOCALAPPDATA'] = $LocalData
    $start.Environment['PATH'] = $pathWithoutVs
    $process = [Diagnostics.Process]::Start($start)
    $deadline = [DateTime]::UtcNow.AddMinutes(3)
    while (-not (Test-Path -LiteralPath $report) -and -not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    if (-not (Test-Path -LiteralPath $report)) {
        $stdout = $process.StandardOutput.ReadToEnd(); $stderr = $process.StandardError.ReadToEnd()
        throw "Packaged voice self-test returned no report. Exit=$($process.ExitCode) stdout=$stdout stderr=$stderr"
    }
    $result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $result.passed) { throw "Packaged voice render failed: $($result.error)" }
    $loaded = @()
    $runtimeDllDirectory = [IO.Path]::GetFullPath((Join-Path $result.resource_root "speech\runtime\piper"))
    foreach ($voice in @($result.voices.uk, $result.voices.us)) {
        if (-not $voice.piper_pid) { throw "Missing Piper PID in packaged render report" }
        $piper = Get-Process -Id ([int]$voice.piper_pid)
        foreach ($module in @($piper.Modules | Where-Object { $_.ModuleName -match '^(VCRUNTIME140(_1)?|MSVCP140)\.dll$' })) {
            if ($module.FileName -match '(?i)\\Microsoft Visual Studio\\|\\VC\\Tools\\MSVC\\') {
                throw "Piper loaded CRT through Visual Studio PATH: $($module.FileName)"
            }
            if (-not $module.FileName.StartsWith($runtimeDllDirectory, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Piper did not load app-local CRT from its runtime directory: $($module.FileName)"
            }
            $loaded += [ordered]@{ piper_pid = $voice.piper_pid; module = $module.ModuleName; path = $module.FileName; sha256 = Get-Sha256 $module.FileName }
        }
    }
    $expectedCrt = @("VCRUNTIME140.dll", "MSVCP140.dll")
    $loadedNames = @($loaded | Select-Object -ExpandProperty module -Unique)
    $missingLoaded = @($expectedCrt | Where-Object { $_ -notin $loadedNames })
    if ($missingLoaded.Count) { throw "Piper did not report loaded CRT modules: $($missingLoaded -join ', ')" }
    Set-Content -LiteralPath $marker -Value "inspected" -Encoding ASCII
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Packaged voice self-test exited $($process.ExitCode)" }
    $result | Add-Member -NotePropertyName crt_modules_loaded -NotePropertyValue $loaded -Force
    $result | Add-Member -NotePropertyName visual_studio_path_removed -NotePropertyValue $true -Force
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $report -Encoding UTF8
    return $result
}

function Install-Setup([string]$Path, [string]$InstallRoot) {
    & $Path /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- "/DIR=$InstallRoot"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code ${LASTEXITCODE}: $Path" }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot "WoerTranslator.exe"))) {
        throw "Inno Setup returned success without installing WoerTranslator.exe"
    }
}

function Write-Json([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$candidateInfo = Get-Item -LiteralPath $resolvedSetup
$sizeLimit = 419430400
if ($candidateInfo.Length -gt $sizeLimit) { throw "Candidate installer exceeds the existing updater cap: $($candidateInfo.Length)" }
$candidateHash = Get-Sha256 $resolvedSetup
$candidateRoot = Join-Path (Split-Path -Parent $resolvedSetup) "..\dist\WoerTranslator"
$candidateCrt = Get-CrtRecords ([IO.Path]::GetFullPath($candidateRoot))

$appRoot = Join-Path $testRoot "安装 Space\Programs\WoerTranslator"
$firstData = Join-Path $testRoot "first-local-app-data"
New-Item -ItemType Directory -Path $firstData,(Split-Path -Parent $appRoot) -Force | Out-Null
$env:LOCALAPPDATA = $firstData
Install-Setup $resolvedSetup $appRoot
Set-InstallTreeAccess $appRoot "ReadOnly"
$firstReadOnly = Assert-ReadOnly $appRoot
$firstAcl = [ordered]@{ root = Get-AclRecord $appRoot; voice_directory = Get-AclRecord (Split-Path -Parent $firstReadOnly.model) }
$firstTreeBefore = Get-TreeDigest $appRoot
$firstSmoke = Invoke-AppVoiceSmoke (Join-Path $appRoot "WoerTranslator.exe") $firstData "first-install"
$firstTreeAfter = Get-TreeDigest $appRoot
if ($firstTreeBefore -ne $firstTreeAfter) { throw "First-install app tree changed while read-only" }

Set-InstallTreeAccess $appRoot "Writable"
$uninstaller = Join-Path $appRoot "unins000.exe"
if (-not (Test-Path -LiteralPath $uninstaller)) { throw "First-install Inno uninstaller is missing" }
& $uninstaller /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
if ($LASTEXITCODE -ne 0) { throw "Candidate uninstaller failed with exit code $LASTEXITCODE" }

$oldName = "WoerTranslator-0.3.22-Windows-x64-Setup.exe"
$oldUrl = "https://github.com/blueaaa333/woer-translator/releases/download/v0.3.22/$oldName"
$checksumsUrl = "https://github.com/blueaaa333/woer-translator/releases/download/v0.3.22/SHA256SUMS.txt"
$oldInstaller = Join-Path $testRoot $oldName
$checksumFile = Join-Path $testRoot "v0.3.22-SHA256SUMS.txt"
Invoke-WebRequest -Uri $checksumsUrl -OutFile $checksumFile
$checksumLine = Get-Content -LiteralPath $checksumFile | Where-Object { $_ -match [regex]::Escape($oldName) } | Select-Object -First 1
if (-not $checksumLine) {
    throw "Could not find the v0.3.22 Windows installer SHA-256 in the published checksum file"
}
if ($checksumLine -match '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') { $oldExpectedHash = $Matches[1].ToLowerInvariant() }
else { throw "Malformed v0.3.22 SHA-256 line: $checksumLine" }
Invoke-WebRequest -Uri $oldUrl -OutFile $oldInstaller
if ((Get-Item -LiteralPath $oldInstaller).Length -ne 58658847 -or (Get-Sha256 $oldInstaller) -ne $oldExpectedHash) {
    throw "Published v0.3.22 installer size or SHA-256 mismatch"
}

$upgradeData = Join-Path $testRoot "upgrade-local-app-data"
New-Item -ItemType Directory -Path $upgradeData -Force | Out-Null
$env:LOCALAPPDATA = $upgradeData
Install-Setup $oldInstaller $appRoot
$oldCrt = Get-CrtRecords $appRoot
$oldAppExe = Join-Path $appRoot "WoerTranslator.exe"
$oldAppHash = Get-Sha256 $oldAppExe
$userRoot = Join-Path $upgradeData "QingCi"
New-Item -ItemType Directory -Path $userRoot -Force | Out-Null
$preferences = Join-Path $userRoot "preferences.json"
$prefsText = '{"auto_read":false,"preferred_accent":1,"accent":0,"prefer_recordings":true,"edge_pdf_auto_copy":false,"all_apps_auto_copy":false}'
[IO.File]::WriteAllText($preferences, $prefsText, [Text.UTF8Encoding]::new($false))
$wordbook = Join-Path $userRoot "生词本.txt"
[IO.File]::WriteAllText($wordbook, "upgrade-probe-word`n", [Text.UTF8Encoding]::new($false))
$partialRoot = Join-Path $userRoot "speech\voices"
$partialUk = Join-Path $partialRoot "uk"
$partialUs = Join-Path $partialRoot "us"
New-Item -ItemType Directory -Path $partialUk,$partialUs -Force | Out-Null
[IO.File]::WriteAllBytes((Join-Path $partialUk "dictionary-voice.onnx"), [byte[]](1,2,3,4))
Copy-Item -LiteralPath "build/voice-package/speech/voices/uk/dictionary-voice.onnx.json" -Destination (Join-Path $partialUk "dictionary-voice.onnx.json")
Copy-Item -LiteralPath "build/voice-package/speech/voices/us/dictionary-voice.onnx.json" -Destination (Join-Path $partialUs "dictionary-voice.onnx.json")
$preferenceHash = Get-Sha256 $preferences
$wordbookHash = Get-Sha256 $wordbook
$partialHashes = @(
    [ordered]@{ path = (Join-Path $partialUk "dictionary-voice.onnx"); sha256 = Get-Sha256 (Join-Path $partialUk "dictionary-voice.onnx") },
    [ordered]@{ path = (Join-Path $partialUk "dictionary-voice.onnx.json"); sha256 = Get-Sha256 (Join-Path $partialUk "dictionary-voice.onnx.json") },
    [ordered]@{ path = (Join-Path $partialUs "dictionary-voice.onnx.json"); sha256 = Get-Sha256 (Join-Path $partialUs "dictionary-voice.onnx.json") }
)

Install-Setup $resolvedSetup $appRoot
if ((Get-Sha256 $preferences) -ne $preferenceHash -or (Get-Sha256 $wordbook) -ne $wordbookHash) {
    throw "v0.3.22-to-candidate upgrade changed user preferences or wordbook"
}
foreach ($item in $partialHashes) {
    if ((Get-Sha256 $item.path) -ne $item.sha256) { throw "Upgrade changed a partial user voice resource: $($item.path)" }
}
if ((Get-Sha256 $oldAppExe) -eq $oldAppHash) { throw "Candidate upgrade did not replace the v0.3.22 application executable" }

Set-InstallTreeAccess $appRoot "ReadOnly"
$readonlyEvidence = Assert-ReadOnly $appRoot
$aclEvidence = [ordered]@{ root = Get-AclRecord $appRoot; voice_directory = Get-AclRecord (Split-Path -Parent $readonlyEvidence.model) }
$treeBefore = Get-TreeDigest $appRoot
$smoke = Invoke-AppVoiceSmoke (Join-Path $appRoot "WoerTranslator.exe") $upgradeData "v0322-upgrade"
$treeAfter = Get-TreeDigest $appRoot
if ($treeBefore -ne $treeAfter) { throw "Upgraded app tree changed during read-only offline voice smoke" }
if ((Get-Sha256 $preferences) -ne $preferenceHash -or (Get-Sha256 $wordbook) -ne $wordbookHash) {
    throw "Offline voice smoke changed preferences or wordbook"
}
foreach ($voice in @($smoke.voices.uk,$smoke.voices.us)) {
    if ($voice.selected_model -notmatch '(_internal|speech)[\\/]speech[\\/]voices|speech[\\/]voices') {
        throw "Partial user voice directory masked the bundled model: $($voice.selected_model)"
    }
}
Set-InstallTreeAccess $appRoot "Writable"

$report = [ordered]@{
    passed = $true
    candidate_installer = [ordered]@{ path = $resolvedSetup; bytes = $candidateInfo.Length; sha256 = $candidateHash; old_updater_cap = $sizeLimit }
    v0_3_22 = [ordered]@{ url = $oldUrl; bytes = (Get-Item -LiteralPath $oldInstaller).Length; sha256 = Get-Sha256 $oldInstaller; install_tree_crt = $oldCrt; old_exe_sha256 = $oldAppHash }
    candidate_pyinstaller_tree_crt = $candidateCrt
    first_install = [ordered]@{ passed = $true; readonly = $firstReadOnly; acl = $firstAcl; tree_sha256_before = $firstTreeBefore; tree_sha256_after = $firstTreeAfter; smoke = $firstSmoke }
    upgrade = [ordered]@{ from = "v0.3.22"; passed = $true; preferences_sha256 = $preferenceHash; wordbook_sha256 = $wordbookHash; partial_voice_hashes = $partialHashes; readonly = $readonlyEvidence; acl = $aclEvidence; tree_sha256_before = $treeBefore; tree_sha256_after = $treeAfter; smoke = $smoke }
    crt_redistribution_rights = "not established; runner-only test DLL copies are not release authorization"
}
Write-Json (Join-Path $resolvedReportRoot "windows-installer-probe.json") $report
Write-Output (ConvertTo-Json $report -Depth 12)

