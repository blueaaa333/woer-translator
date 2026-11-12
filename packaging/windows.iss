#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef MsvcRuntimeMinimumMajor
  #define MsvcRuntimeMinimumMajor 0
#endif
#ifndef MsvcRuntimeMinimumMinor
  #define MsvcRuntimeMinimumMinor 0
#endif
#ifndef MsvcRuntimeMinimumBuild
  #define MsvcRuntimeMinimumBuild 0
#endif
#ifndef MsvcRuntimeMinimumRevision
  #define MsvcRuntimeMinimumRevision 0
#endif
#ifdef ProbeInstaller
  #ifdef ProbeForceMissingMsvcRuntime
    #define InstallerOutputName "WoerTranslator-MsvcRuntime-Missing-Probe"
  #else
    #ifdef ProbeReadyMsvcRuntime
      #define InstallerOutputName "WoerTranslator-MsvcRuntime-Ready-Probe"
    #else
      #define InstallerOutputName "WoerTranslator-MsvcRuntime-TooOld-Probe"
    #endif
  #endif
#else
  #define InstallerOutputName "WoerTranslator-" + AppVersion + "-Windows-x64-Setup"
#endif
[Setup]
AppId={{D613C38F-914D-419B-B07F-1853FD68938A}
AppName=沃尔翻译官
AppVersion={#AppVersion}
AppPublisher=Woer Translator contributors
AppPublisherURL=https://github.com/blueaaa333/woer-translator
DefaultDirName={localappdata}\Programs\WoerTranslator
DefaultGroupName=沃尔翻译官
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release-assets
OutputBaseFilename={#InstallerOutputName}
SetupIconFile=..\assets\沃尔翻译官.ico
UninstallDisplayIcon={app}\WoerTranslator.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=..\packaging\INSTALL-NOTICE.txt
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#ifdef RequireMsvcRuntime
[InstallDelete]
; Remove only this application's previously bundled copies before installing
; the system-CRT build. These paths are confined to {app}; never touch Windows.
Type: files; Name: "{app}\_internal\VCRUNTIME140.dll"
Type: files; Name: "{app}\_internal\VCRUNTIME140_1.dll"
Type: files; Name: "{app}\_internal\MSVCP140.dll"
Type: files; Name: "{app}\_internal\speech\runtime\piper\VCRUNTIME140.dll"
Type: files; Name: "{app}\_internal\speech\runtime\piper\VCRUNTIME140_1.dll"
Type: files; Name: "{app}\_internal\speech\runtime\piper\MSVCP140.dll"
#endif
[Files]
Source: "..\dist\WoerTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Icons]
Name: "{group}\沃尔翻译官"; Filename: "{app}\WoerTranslator.exe"
Name: "{autodesktop}\沃尔翻译官"; Filename: "{app}\WoerTranslator.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\WoerTranslator.exe"; Description: "Open Woer Translator"; Flags: nowait postinstall skipifsilent unchecked
[Code]
#ifdef RequireMsvcRuntime
const
  MsvcRuntimeRegistryKey = 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';
  MsvcRuntimeDownloadUrl = 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170';

function VersionAtLeast(AMajor, AMinor, ABuild, ARevision: Cardinal): Boolean;
begin
  Result :=
    (AMajor > {#MsvcRuntimeMinimumMajor}) or
    ((AMajor = {#MsvcRuntimeMinimumMajor}) and (AMinor > {#MsvcRuntimeMinimumMinor})) or
    ((AMajor = {#MsvcRuntimeMinimumMajor}) and (AMinor = {#MsvcRuntimeMinimumMinor}) and (ABuild > {#MsvcRuntimeMinimumBuild})) or
    ((AMajor = {#MsvcRuntimeMinimumMajor}) and (AMinor = {#MsvcRuntimeMinimumMinor}) and
     (ABuild = {#MsvcRuntimeMinimumBuild}) and (ARevision >= {#MsvcRuntimeMinimumRevision}));
end;

function SystemMsvcRuntimeReady(var InstalledVersion: String): Boolean;
var
  Installed, Major, Minor, Build, Revision: Cardinal;
begin
  Result := False;
  InstalledVersion := 'not installed';
  if not RegQueryDWordValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Installed', Installed) then
    Exit;
  if Installed <> 1 then
    Exit;
  if not RegQueryDWordValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Major', Major) then Exit;
  if not RegQueryDWordValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Minor', Minor) then Exit;
  if not RegQueryDWordValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Bld', Build) then Exit;
  if not RegQueryDWordValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Rbld', Revision) then Exit;
  RegQueryStringValue(HKEY_LOCAL_MACHINE_64, MsvcRuntimeRegistryKey, 'Version', InstalledVersion);
  if not FileExists(ExpandConstant('{sys}\VCRUNTIME140.dll')) then Exit;
  if not FileExists(ExpandConstant('{sys}\VCRUNTIME140_1.dll')) then Exit;
  if not FileExists(ExpandConstant('{sys}\MSVCP140.dll')) then Exit;
  Result := VersionAtLeast(Major, Minor, Build, Revision);
end;
#endif

function InitializeSetup(): Boolean;
var
  Ready: Boolean;
  InstalledVersion: String;
  RequiredVersion: String;
  MessageText: String;
begin
  Result := True;
#ifdef RequireMsvcRuntime
  RequiredVersion := '{#MsvcRuntimeMinimumMajor}.{#MsvcRuntimeMinimumMinor}.{#MsvcRuntimeMinimumBuild}.{#MsvcRuntimeMinimumRevision}';
  InstalledVersion := 'not installed';
#ifdef ProbeForceMissingMsvcRuntime
  Ready := False;
#else
  Ready := SystemMsvcRuntimeReady(InstalledVersion);
#endif
  if not Ready then
  begin
    MessageText := '沃尔翻译官需要已安装的 Microsoft Visual C++ x64 运行库，版本至少为 ' + RequiredVersion + '.' + #13#10 +
      '当前检测到：' + InstalledVersion + '.' + #13#10#13#10 +
      '请先从微软官方下载页面独立安装 x64 版本，然后重新运行安装程序：' + #13#10 + MsvcRuntimeDownloadUrl;
    Log('MSVC x64 prerequisite failed. Required=' + RequiredVersion + '; installed=' + InstalledVersion + '; url=' + MsvcRuntimeDownloadUrl);
    if not WizardSilent then
      MsgBox(MessageText, mbError, MB_OK);
    Result := False;
  end;
#endif
end;
