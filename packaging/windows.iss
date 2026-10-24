#ifndef AppVersion
  #define AppVersion "0.2.0"
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
OutputBaseFilename=WoerTranslator-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\assets\沃尔翻译官.ico
UninstallDisplayIcon={app}\WoerTranslator.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=..\packaging\INSTALL-NOTICE.txt
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Files]
Source: "..\dist\WoerTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Icons]
Name: "{group}\沃尔翻译官"; Filename: "{app}\WoerTranslator.exe"
Name: "{autodesktop}\沃尔翻译官"; Filename: "{app}\WoerTranslator.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\WoerTranslator.exe"; Description: "Open Woer Translator"; Flags: nowait postinstall skipifsilent unchecked
