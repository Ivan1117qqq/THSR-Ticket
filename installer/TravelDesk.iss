#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif
[Setup]
AppId={{757AC553-6205-4B6B-ACB3-C6F68972804B}
AppName=Travel Desk
AppVersion={#AppVersion}
AppPublisher=Travel Desk Project
DefaultDirName={localappdata}\Programs\TravelDesk
DefaultGroupName=Travel Desk
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=TravelDesk-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\build\icons\app.ico
UninstallDisplayIcon={app}\TravelDesk.exe
CloseApplications=no
RestartApplications=no
SetupMutex=TravelDeskInstaller
AppMutex=TravelDeskRunning

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesetraditional"; MessagesFile: "compiler:Default.isl,TraditionalChinese.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; Flags: unchecked

[Files]
Source: "..\dist\TravelDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Travel Desk"; Filename: "{app}\TravelDesk.exe"
Name: "{autodesktop}\Travel Desk"; Filename: "{app}\TravelDesk.exe"; Tasks: desktopicon

; User preferences/config/state/runs live outside {app}. No UninstallDelete rules.
; Never auto-kill a running booking to install an update.
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if CheckForMutexes('TravelDeskRunning') then
    Result := '請等待目前訂位結束並關閉 Travel Desk，再重新執行安裝。';
end;
