; Optional Inno Setup installer, after build_exe.bat created the onedir folder.
#define AppName "NeonTube Downloader"
#define AppVersion "1.36.0"
#define AppExe "NeonTubeDownloader.exe"

[Setup]
AppId=NeonTubeDownloader
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=NeonTube Project
DefaultDirName={localappdata}\Programs\NeonTubeDownloader
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=NeonTubeDownloader_Setup_V1_36_0
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "dist\NeonTubeDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknuepfung erstellen"; GroupDescription: "Weitere Optionen:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "NeonTube Downloader starten"; Flags: nowait postinstall skipifsilent
