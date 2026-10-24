param([switch]$WithSpeech)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if(-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')){
    python -m venv .venv
    if($LASTEXITCODE -ne 0){throw 'Creating Python environment failed'}
}
$python=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $python -m pip install -r requirements.txt
if($LASTEXITCODE -ne 0){throw 'Installing Python dependencies failed'}
& $python scripts/prepare_data.py
if($LASTEXITCODE -ne 0){throw 'Preparing dictionaries failed'}
& (Join-Path $PSScriptRoot 'build_bridge.ps1')
if($WithSpeech){
    & $python scripts/setup_speech.py
    if($LASTEXITCODE -ne 0){throw 'Installing optional speech dependencies failed'}
}
Start-Process -FilePath (Join-Path $PSScriptRoot '.venv/Scripts/pythonw.exe') -ArgumentList 'app.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
