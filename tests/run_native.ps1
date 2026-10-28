$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
& (Join-Path $project 'build_bridge.ps1')
$compiler='C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$lifecycle=Join-Path $PSScriptRoot 'LifecyclePolicyTests.exe'
$normalization=Join-Path $PSScriptRoot 'QueryNormalizationTests.exe'
& $compiler /nologo "/out:$lifecycle" (Join-Path $PSScriptRoot 'LifecyclePolicyTests.cs') (Join-Path $project 'ToolbarLifecyclePolicy.cs')
if($LASTEXITCODE -ne 0){throw 'Lifecycle test compilation failed'}
& $lifecycle
if($LASTEXITCODE -ne 0){throw 'Lifecycle tests failed'}
& $compiler /nologo "/out:$normalization" (Join-Path $PSScriptRoot 'QueryNormalizationTests.cs')
if($LASTEXITCODE -ne 0){throw 'Normalization test compilation failed'}
& $normalization (Join-Path $project 'DesktopBridge.exe')
if($LASTEXITCODE -ne 0){throw 'Normalization tests failed'}

$selection=Join-Path $PSScriptRoot 'SelectionRangeTests.exe'
& $compiler /nologo "/out:$selection" (Join-Path $PSScriptRoot 'SelectionRangeTests.cs') (Join-Path $project 'ToolbarLifecyclePolicy.cs')
if($LASTEXITCODE -ne 0){throw 'Selection range tests compilation failed'}
& $selection
if($LASTEXITCODE -ne 0){throw 'Selection range tests failed'}
$browser=Join-Path $PSScriptRoot 'BrowserTextSelectionTests.exe'
& $compiler /nologo /r:Accessibility.dll "/out:$browser" (Join-Path $PSScriptRoot 'BrowserTextSelectionTests.cs') (Join-Path $project 'BrowserTextSelection.cs') (Join-Path $project 'ToolbarLifecyclePolicy.cs')
if($LASTEXITCODE -ne 0){throw 'Browser selection test compilation failed'}
& $browser
if($LASTEXITCODE -ne 0){throw 'Browser selection tests failed'}
$office=Join-Path $PSScriptRoot 'OfficeSelectionTests.exe'
& $compiler /nologo /r:Microsoft.CSharp.dll "/out:$office" (Join-Path $PSScriptRoot 'OfficeSelectionTests.cs') (Join-Path $project 'OfficeSelection.cs')
if($LASTEXITCODE -ne 0){throw 'Office selection test compilation failed'}
& $office
if($LASTEXITCODE -ne 0){throw 'Office selection tests failed'}
