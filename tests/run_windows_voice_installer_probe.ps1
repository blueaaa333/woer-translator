param(
    [Parameter(Mandatory=$false)][string]$CandidateSetup = "",
    [Parameter(Mandatory=$false)][string]$MissingRuntimeSetup = "",
    [Parameter(Mandatory=$false)][string]$TooOldRuntimeSetup = "",
    [Parameter(Mandatory=$false)][string]$MinimumRuntimeVersion = "",
    [Parameter(Mandatory=$false)][switch]$SelfTestProcessTimeout,
    [Parameter(Mandatory=$false)][string]$ReportRoot = "build/voice-package-review"
)
$ErrorActionPreference = "Stop"

$runnerTemp = [IO.Path]::GetFullPath($env:RUNNER_TEMP)
$testRoot = [IO.Path]::GetFullPath((Join-Path $runnerTemp "woer-voice-installer-probe"))
if (-not $testRoot.StartsWith($runnerTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Probe root is outside RUNNER_TEMP: $testRoot"
}
$resolvedSetup = if ($CandidateSetup) { [IO.Path]::GetFullPath($CandidateSetup) } else { "" }
$resolvedReportRoot = [IO.Path]::GetFullPath($ReportRoot)
New-Item -ItemType Directory -Path $testRoot,$resolvedReportRoot -Force | Out-Null
$script:processEvents = @()

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CrtRecords([string]$Root) {
    $names = @("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")
    $lowerNames = @($names | ForEach-Object { $_.ToLowerInvariant() })
    $records = @()
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $records }
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force -ErrorAction SilentlyContinue)) {
        $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($file.FullName)
        $original = if ($info.OriginalFilename) { [IO.Path]::GetFileName($info.OriginalFilename).ToLowerInvariant() } else { "" }
        if ($lowerNames -notcontains $file.Name.ToLowerInvariant() -and $lowerNames -notcontains $original) { continue }
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
        $records += [ordered]@{
            name = $file.Name
            original_filename = $info.OriginalFilename
            path = $file.FullName
            bytes = $file.Length
            sha256 = Get-Sha256 $file.FullName
            file_version = $info.FileVersion
            signature_status = [string]$signature.Status
            signer = $subject
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
    $stdoutLog = Join-Path $resolvedReportRoot "$Label-voice-smoke.stdout.txt"
    $stderrLog = Join-Path $resolvedReportRoot "$Label-voice-smoke.stderr.txt"
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
    $stdoutWriter = [IO.StreamWriter]::new($stdoutLog, $false, [Text.UTF8Encoding]::new($false))
    $stderrWriter = [IO.StreamWriter]::new($stderrLog, $false, [Text.UTF8Encoding]::new($false))
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $process.add_OutputDataReceived([Diagnostics.DataReceivedEventHandler]{ param($sender,$eventArgs) if ($null -ne $eventArgs.Data) { $stdoutWriter.WriteLine($eventArgs.Data); $stdoutWriter.Flush() } })
    $process.add_ErrorDataReceived([Diagnostics.DataReceivedEventHandler]{ param($sender,$eventArgs) if ($null -ne $eventArgs.Data) { $stderrWriter.WriteLine($eventArgs.Data); $stderrWriter.Flush() } })
    $started = [DateTime]::UtcNow
    $processStarted = $false
    try {
        [void]$process.Start()
        $processStarted = $true
        Write-ProcessEvent ([ordered]@{ stage = "voice-$Label"; event = "start"; pid = $process.Id; started_utc = $started.ToString("o"); timeout_seconds = 240 })
        $process.BeginOutputReadLine(); $process.BeginErrorReadLine()
        $deadline = $started.AddMinutes(4)
        while (-not (Test-Path -LiteralPath $report) -and -not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 200
        }
        if (-not (Test-Path -LiteralPath $report)) {
            throw "Packaged voice self-test returned no report within 240 seconds"
        }
        $result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $result.passed) { throw "Packaged voice render failed: $($result.error)" }
        $loaded = @()
        $systemCrtDirectory = [IO.Path]::GetFullPath((Join-Path $env:SystemRoot "System32")).TrimEnd("\") + "\"
        $processes = @([ordered]@{ role = "frozen-app"; process = $process })
        foreach ($voice in @($result.voices.uk, $result.voices.us)) {
            if (-not $voice.piper_pid) { throw "Missing Piper PID in packaged render report" }
            $processes += [ordered]@{ role = "piper-$($voice.accent)"; process = (Get-Process -Id ([int]$voice.piper_pid)) }
        }
        foreach ($entry in $processes) {
            foreach ($module in @($entry.process.Modules | Where-Object { $_.ModuleName -match '^(VCRUNTIME140(_1)?|MSVCP140)\.dll$' })) {
                if (-not $module.FileName.StartsWith($systemCrtDirectory, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "$($entry.role) loaded CRT outside the system x64 runtime directory: $($module.FileName)"
                }
                $loaded += [ordered]@{
                    role = $entry.role; process_id = $entry.process.Id; module = $module.ModuleName
                    path = $module.FileName; bytes = (Get-Item -LiteralPath $module.FileName).Length
                    sha256 = Get-Sha256 $module.FileName
                    file_version = [Diagnostics.FileVersionInfo]::GetVersionInfo($module.FileName).FileVersion
                    signature_status = [string](Get-AuthenticodeSignature -LiteralPath $module.FileName).Status
                }
            }
        }
        $expectedCrt = @("VCRUNTIME140.dll", "MSVCP140.dll")
        $loadedNames = @($loaded | ForEach-Object { $_["module"] } | Select-Object -Unique)
        $missingLoaded = @($expectedCrt | Where-Object { $_ -notin $loadedNames })
        if ($missingLoaded.Count) { throw "Frozen app or Piper did not report loaded system CRT modules: $($missingLoaded -join ', ')" }
        Set-Content -LiteralPath $marker -Value "inspected" -Encoding ASCII
        if (-not $process.WaitForExit(30000)) { throw "Packaged voice self-test did not exit within 30 seconds after report inspection" }
        [void]$process.WaitForExit()
        if ($process.ExitCode -ne 0) { throw "Packaged voice self-test exited $($process.ExitCode); stdout=$stdoutLog; stderr=$stderrLog" }
        Write-ProcessEvent ([ordered]@{ stage = "voice-$Label"; pid = $process.Id; started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o"); exit_code = $process.ExitCode; timeout_seconds = 240; timed_out = $false; stdout_log = $stdoutLog; stderr_log = $stderrLog })
        $result | Add-Member -NotePropertyName crt_modules_loaded -NotePropertyValue $loaded -Force
        $result | Add-Member -NotePropertyName system_crt_directory -NotePropertyValue $systemCrtDirectory.TrimEnd("\") -Force
        $result | Add-Member -NotePropertyName visual_studio_path_removed -NotePropertyValue $true -Force
        $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $report -Encoding UTF8
        return $result
    } catch {
        $treeTerminated = $false
        if ($processStarted) {
            $process.Refresh()
            if (-not $process.HasExited) {
                if ((Test-Path -LiteralPath $report) -and -not (Test-Path -LiteralPath $marker)) {
                    Set-Content -LiteralPath $marker -Value "failure-cleanup" -Encoding ASCII
                }
                if (-not $process.WaitForExit(5000)) {
                    $treeTerminated = Stop-TestProcessTree $process.Id
                    [void]$process.WaitForExit(10000)
                    $process.Refresh()
                }
            }
        }
        $hasExited = $false
        $exitCode = $null
        if ($processStarted) {
            $process.Refresh()
            $hasExited = $process.HasExited
            if ($hasExited) { $exitCode = $process.ExitCode }
        }
        $elapsed = ([DateTime]::UtcNow - $started).TotalSeconds
        $timeoutStage = if (-not (Test-Path -LiteralPath $report) -and $elapsed -ge 240) { "report" } elseif ((Test-Path -LiteralPath $report) -and -not $hasExited) { "post-report-exit" } else { $null }
        $failure = [ordered]@{
            stage = "voice-$Label"; pid = if ($processStarted) { $process.Id } else { $null }
            started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o")
            elapsed_seconds = [Math]::Round($elapsed, 2); timeout_stage = $timeoutStage
            timeout_seconds = if ($timeoutStage -eq "report") { 240 } elseif ($timeoutStage -eq "post-report-exit") { 30 } else { $null }
            timed_out = ($null -ne $timeoutStage); tree_terminated = $treeTerminated; process_exited = $hasExited
            exit_code = $exitCode; report_exists = (Test-Path -LiteralPath $report)
            stdout_log = $stdoutLog; stderr_log = $stderrLog; error = $_.Exception.Message
        }
        Write-ProcessEvent $failure
        Write-Json (Join-Path $resolvedReportRoot "$Label-voice-smoke-failure.json") $failure
        throw
    } finally {
        if ($processStarted -and $process.HasExited) { [void]$process.WaitForExit() }
        $stdoutWriter.Dispose(); $stderrWriter.Dispose(); $process.Dispose()
    }
}

function Install-Setup([string]$Path, [string]$InstallRoot) {
    $logName = "inno-install-{0}.log" -f ([Guid]::NewGuid().ToString("N"))
    $installLog = Join-Path $resolvedReportRoot $logName
    $stageName = "install-" + [IO.Path]::GetFileNameWithoutExtension($Path)
    $arguments = @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        "/LOG=`"$installLog`"", "/DIR=`"$InstallRoot`""
    )
    $started = [DateTime]::UtcNow
    try { $run = Invoke-BoundedProcess -Name $stageName -FilePath $Path -Arguments $arguments -TimeoutSeconds 300 }
    catch {
        $logTail = if (Test-Path -LiteralPath $installLog -PathType Leaf) { (Get-Content -LiteralPath $installLog -Tail 80) -join "`n" } else { "<Inno log was not created>" }
        $failure = [ordered]@{ stage = $stageName; installer = $Path; requested_install_root = $InstallRoot; started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o"); timeout_seconds = 300; executable_exists = (Test-Path -LiteralPath (Join-Path $InstallRoot "WoerTranslator.exe")); inno_log_path = $installLog; inno_log_tail = $logTail; error = $_.Exception.Message }
        Write-Json (Join-Path $resolvedReportRoot "installer-failure.json") $failure
        throw
    }
    $installer = $run.process
    $exitCode = $installer.ExitCode
    if ($exitCode -ne 0) {
        $logTail = if (Test-Path -LiteralPath $installLog -PathType Leaf) { (Get-Content -LiteralPath $installLog -Tail 80) -join "`n" } else { "<Inno log was not created>" }
        $failure = [ordered]@{ stage = $stageName; installer = $Path; requested_install_root = $InstallRoot; pid = $installer.Id; started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o"); exit_code = $exitCode; timeout_seconds = 300; executable_exists = (Test-Path -LiteralPath (Join-Path $InstallRoot "WoerTranslator.exe")); inno_log_path = $installLog; inno_log_tail = $logTail }
        Write-Json (Join-Path $resolvedReportRoot "installer-failure.json") $failure
        throw "Inno Setup failed with exit code ${exitCode}: $Path; log=$installLog"
    }
    $expectedExe = Join-Path $InstallRoot "WoerTranslator.exe"
    if (-not (Test-Path -LiteralPath $expectedExe -PathType Leaf)) {
        $searchRoots = @($InstallRoot, (Join-Path $env:LOCALAPPDATA "Programs\WoerTranslator"), $testRoot) |
            Select-Object -Unique
        $foundExes = @()
        foreach ($searchRoot in $searchRoots) {
            if (Test-Path -LiteralPath $searchRoot -PathType Container) {
                $foundExes += @(Get-ChildItem -LiteralPath $searchRoot -Filter "WoerTranslator.exe" -File -Recurse -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty FullName)
            }
        }
        $logTail = if (Test-Path -LiteralPath $installLog -PathType Leaf) {
            (Get-Content -LiteralPath $installLog -Tail 80) -join "`n"
        } else { "<Inno log was not created>" }
        $failure = [ordered]@{
            installer = $Path
            requested_install_root = $InstallRoot
            expected_executable = $expectedExe
            exit_code = $exitCode
            process_waited = $true
            found_executables = $foundExes
            inno_log_path = $installLog
            inno_log_tail = $logTail
        }
        $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedReportRoot "installer-failure.json") -Encoding UTF8
        throw "Inno Setup returned success without installing WoerTranslator.exe at the requested path; see installer-failure.json"
    }
}

function Write-Json([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Write-ProcessEvent($Event) {
    $script:processEvents += $Event
    Write-Json (Join-Path $resolvedReportRoot "process-events.json") ([ordered]@{ events = $script:processEvents })
}

function Stop-TestProcessTree([int]$ProcessId) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return $true }
    try {
        $process.Kill($true)
        if ($process.WaitForExit(10000)) { return $true }
    } catch {
        $killTreeError = $_.Exception.Message
    }
    $taskkill = Join-Path $env:SystemRoot "System32/taskkill.exe"
    & $taskkill /PID $ProcessId /T /F 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { return $true }
    return (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue))
}

function Invoke-BoundedProcess([string]$Name, [string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds, [switch]$AllowTimeout) {
    $started = [DateTime]::UtcNow
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    $processId = $process.Id
    Write-ProcessEvent ([ordered]@{ stage = $Name; event = "start"; file = $FilePath; arguments = $Arguments; pid = $processId; started_utc = $started.ToString("o"); timeout_seconds = $TimeoutSeconds })
    $deadline = $started.AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
        $process.Refresh()
    }
    $timedOut = -not $process.HasExited
    $treeTerminated = $false
    if ($timedOut) {
        $treeTerminated = Stop-TestProcessTree $processId
        [void]$process.WaitForExit(10000)
        $process.Refresh()
    }
    $processStopped = $process.HasExited
    $event = [ordered]@{
        stage = $Name; file = $FilePath; arguments = $Arguments; pid = $processId
        started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o")
        exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
        timeout_seconds = $TimeoutSeconds; timed_out = $timedOut; tree_terminated = $treeTerminated; process_stopped = $processStopped
    }
    Write-ProcessEvent $event
    if ($timedOut -and (-not $AllowTimeout -or -not $processStopped)) {
        Write-Json (Join-Path $resolvedReportRoot "$Name-timeout-failure.json") $event
        throw "Timed out after $TimeoutSeconds seconds in process stage '$Name'; pid=$processId; tree_terminated=$treeTerminated"
    }
    return [pscustomobject]@{ process = $process; event = $event; timed_out = $timedOut }
}

function Assert-BlockedPrerequisiteSetup([string]$SetupPath, [string]$Label, [bool]$Interactive,
    [string]$ExistingInstallRoot = "", [string]$ExpectedExistingExeSha256 = "") {
    if (-not (Test-Path -LiteralPath $SetupPath -PathType Leaf)) { throw "Prerequisite fixture installer is missing: $SetupPath" }
    $destination = if ($ExistingInstallRoot) { [IO.Path]::GetFullPath($ExistingInstallRoot) } else { Join-Path $testRoot "$Label-install" }
    $existingExe = Join-Path $destination "WoerTranslator.exe"
    $beforeExeHash = if (Test-Path -LiteralPath $existingExe -PathType Leaf) { Get-Sha256 $existingExe } else { "" }
    if ($ExpectedExistingExeSha256 -and $beforeExeHash -ne $ExpectedExistingExeSha256) {
        throw "$Label fixture did not start from the expected existing installation"
    }
    $log = Join-Path $resolvedReportRoot "$Label-inno.log"
    $arguments = @("/LOG=`"$log`"", "/DIR=`"$destination`"")
    if (-not $Interactive) { $arguments += @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") }
    $started = [DateTime]::UtcNow
    $installer = Start-Process -FilePath $SetupPath -ArgumentList $arguments -PassThru
    Write-ProcessEvent ([ordered]@{ stage = $Label; event = "start"; installer = $SetupPath; pid = $installer.Id; started_utc = $started.ToString("o"); timeout_seconds = 30 })
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $sentEnter = $false
    while (-not $installer.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        $installer.Refresh()
        if ($Interactive -and -not $sentEnter -and $installer.MainWindowHandle -ne [IntPtr]::Zero) {
            $shell = New-Object -ComObject WScript.Shell
            [void]$shell.AppActivate($installer.Id)
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            $sentEnter = $true
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $installer.HasExited) {
        $treeTerminated = Stop-TestProcessTree $installer.Id
        [void]$installer.WaitForExit(10000)
        $failure = [ordered]@{ stage = $Label; installer = $SetupPath; pid = $installer.Id; started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o"); timeout_seconds = 30; timed_out = $true; tree_terminated = $treeTerminated; inno_log_path = $log }
        Write-ProcessEvent $failure
        Write-Json (Join-Path $resolvedReportRoot "$Label-timeout-failure.json") $failure
        throw "$Label prerequisite installer did not exit after the blocking check"
    }
    Write-ProcessEvent ([ordered]@{ stage = $Label; installer = $SetupPath; pid = $installer.Id; started_utc = $started.ToString("o"); ended_utc = [DateTime]::UtcNow.ToString("o"); timeout_seconds = 30; timed_out = $false; exit_code = $installer.ExitCode; interactive = $Interactive })
    if ($installer.ExitCode -eq 0) { throw "$Label prerequisite installer unexpectedly succeeded" }
    if ($ExpectedExistingExeSha256) {
        if (-not (Test-Path -LiteralPath $existingExe -PathType Leaf) -or (Get-Sha256 $existingExe) -ne $beforeExeHash) {
            throw "$Label prerequisite installer changed the existing application before blocking"
        }
    } elseif (Test-Path -LiteralPath $existingExe -PathType Leaf) {
        throw "$Label prerequisite installer modified the destination before blocking"
    }
    $logText = if (Test-Path -LiteralPath $log -PathType Leaf) { Get-Content -LiteralPath $log -Raw } else { "" }
    if ($logText -notmatch "MSVC x64 prerequisite failed") { throw "$Label installer log did not record the CRT prerequisite block" }
    return [ordered]@{
        blocked = $true; interactive = $Interactive; exit_code = $installer.ExitCode
        destination_created = (Test-Path -LiteralPath $destination)
        inno_log = $log; message_logged = $true; enter_sent = $sentEnter
    }
}

if ($SelfTestProcessTimeout) {
    $hostExecutable = (Get-Process -Id $PID).Path
    $timeoutProbe = Invoke-BoundedProcess -Name "timeout-fixture" -FilePath $hostExecutable `
        -Arguments @("-NoProfile", "-Command", "Start-Sleep -Seconds 30") -TimeoutSeconds 2 -AllowTimeout
    if (-not $timeoutProbe.timed_out -or -not $timeoutProbe.event.tree_terminated -or -not $timeoutProbe.event.process_stopped) {
        throw "Non-exiting process timeout fixture was not terminated as expected"
    }
    Write-Json (Join-Path $resolvedReportRoot "process-timeout-self-test.json") ([ordered]@{
        passed = $true; process = $timeoutProbe.event
    })
    Write-Output "Bounded child process timeout/cleanup fixture passed"
    exit 0
}

if (-not $resolvedSetup -or -not $MissingRuntimeSetup -or -not $TooOldRuntimeSetup -or -not $MinimumRuntimeVersion) {
    throw "Candidate setup, both prerequisite fixtures, and minimum runtime version are required"
}

$candidateInfo = Get-Item -LiteralPath $resolvedSetup
$sizeLimit = 419430400
if ($candidateInfo.Length -gt $sizeLimit) { throw "Candidate installer exceeds the existing updater cap: $($candidateInfo.Length)" }
$candidateHash = Get-Sha256 $resolvedSetup
$candidateRoot = Join-Path (Split-Path -Parent $resolvedSetup) "..\dist\WoerTranslator"
$candidateCrt = Get-CrtRecords ([IO.Path]::GetFullPath($candidateRoot))
if ($candidateCrt.Count -gt 0) { throw "Candidate PyInstaller tree still contains MSVC CRT copies: $($candidateCrt.path -join ', ')" }
$missingPrerequisite = Assert-BlockedPrerequisiteSetup $MissingRuntimeSetup "missing-runtime" $true

$appRoot = Join-Path $testRoot "安装 Space\Programs\WoerTranslator"
$firstData = Join-Path $testRoot "first-local-app-data"
New-Item -ItemType Directory -Path $firstData,(Split-Path -Parent $appRoot) -Force | Out-Null
$env:LOCALAPPDATA = $firstData
Install-Setup $resolvedSetup $appRoot
$firstInstalledCrt = Get-CrtRecords $appRoot
if ($firstInstalledCrt.Count -gt 0) { throw "First install contains app-local MSVC CRT copies: $($firstInstalledCrt.path -join ', ')" }
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
$uninstallRun = Invoke-BoundedProcess -Name "candidate-uninstall" -FilePath $uninstaller `
    -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -TimeoutSeconds 180
if ($uninstallRun.process.ExitCode -ne 0) { throw "Candidate uninstaller failed with exit code $($uninstallRun.process.ExitCode)" }

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
$tooOldPrerequisite = Assert-BlockedPrerequisiteSetup $TooOldRuntimeSetup "too-old-runtime" $false $appRoot $oldAppHash
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
$upgradedInstalledCrt = Get-CrtRecords $appRoot
if ($upgradedInstalledCrt.Count -gt 0) { throw "Upgrade left app-local MSVC CRT copies: $($upgradedInstalledCrt.path -join ', ')" }

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
    candidate_installer = [ordered]@{ path = $resolvedSetup; bytes = $candidateInfo.Length; sha256 = $candidateHash; old_updater_cap = $sizeLimit; minimum_system_runtime = $MinimumRuntimeVersion }
    prerequisite_fixtures = [ordered]@{ interactive_missing_runtime = $missingPrerequisite; silent_too_old_runtime = $tooOldPrerequisite }
    system_crt = (Get-Content -LiteralPath (Join-Path $resolvedReportRoot "system-crt-prerequisite.json") -Raw | ConvertFrom-Json)
    installed_tree_crt_after_first_install = $firstInstalledCrt
    installed_tree_crt_after_upgrade = $upgradedInstalledCrt
    v0_3_22 = [ordered]@{ url = $oldUrl; bytes = (Get-Item -LiteralPath $oldInstaller).Length; sha256 = Get-Sha256 $oldInstaller; install_tree_crt = $oldCrt; old_exe_sha256 = $oldAppHash }
    candidate_pyinstaller_tree_crt = $candidateCrt
    first_install = [ordered]@{ passed = $true; readonly = $firstReadOnly; acl = $firstAcl; tree_sha256_before = $firstTreeBefore; tree_sha256_after = $firstTreeAfter; smoke = $firstSmoke }
    upgrade = [ordered]@{ from = "v0.3.22"; passed = $true; preferences_sha256 = $preferenceHash; wordbook_sha256 = $wordbookHash; partial_voice_hashes = $partialHashes; readonly = $readonlyEvidence; acl = $aclEvidence; tree_sha256_before = $treeBefore; tree_sha256_after = $treeAfter; smoke = $smoke }
    crt_redistribution_rights = "not established; runner-only test DLL copies are not release authorization"
}
Write-Json (Join-Path $resolvedReportRoot "windows-installer-probe.json") $report
Write-Output (ConvertTo-Json $report -Depth 12)

