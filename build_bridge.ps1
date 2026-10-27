$ErrorActionPreference='Stop'
$framework='C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$source=Join-Path $PSScriptRoot 'DesktopBridge.cs'
$policy=Join-Path $PSScriptRoot 'ToolbarLifecyclePolicy.cs'
$browser=Join-Path $PSScriptRoot 'BrowserTextSelection.cs'
$bridge=Join-Path $PSScriptRoot 'DesktopBridge.exe'
& (Join-Path $framework 'csc.exe') /nologo /target:exe "/out:$bridge" /r:Accessibility.dll /r:Microsoft.CSharp.dll /r:System.Windows.Forms.dll "/r:$framework\WPF\UIAutomationClient.dll" "/r:$framework\WPF\UIAutomationTypes.dll" "/r:$framework\WPF\WindowsBase.dll" $source $policy $browser
if($LASTEXITCODE -ne 0){throw 'Native helper build failed'}
