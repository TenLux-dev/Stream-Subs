[Setup]
AppComments=При первом запуске потребуется скачать ~4 ГБ. On first launch about 4 GB will be downloaded.
AppName=Stream Subs (CPU)
AppVersion=1.2.0
AppPublisher=CJDARKLORD
AppPublisherURL=https://github.com/CJDARKLORD/Stream-Subs
DefaultDirName={autopf}\StreamSubsCPU
DefaultGroupName=Stream Subs (CPU)
UninstallDisplayIcon={app}\StreamSubs.exe
OutputDir=E:\stream-subs\installer_output
OutputBaseFilename=StreamSubsSetup-CPU
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern
InfoBeforeFile=E:\stream-subs\README.txt
SetupIconFile=E:\stream-subs\app.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "E:\stream-subs\dist\StreamSubs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\stream-subs\python-embedded\*"; DestDir: "{app}\python-embedded"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\stream-subs\web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\stream-subs\lists\*"; DestDir: "{app}\lists"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\stream-subs\config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "E:\stream-subs\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "E:\stream-subs\app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon / Создать ярлык на рабочем столе"; GroupDescription: "Additional icons / Дополнительные ярлыки"

[Icons]
Name: "{group}\Stream Subs"; Filename: "{app}\StreamSubs.exe"; Parameters: "--cpu --desktop"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"
Name: "{group}\Uninstall Stream Subs"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Stream Subs"; Filename: "{app}\StreamSubs.exe"; Parameters: "--cpu --desktop"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\StreamSubs.exe"; Parameters: "--cpu --desktop"; Description: "Launch Stream Subs / Запустить Stream Subs"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\__pycache__"