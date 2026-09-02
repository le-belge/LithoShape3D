; Script Inno Setup pour LithoShape3D (Windows).
; Emballe le dossier PyInstaller (packaging\dist\LithoShape3D\) dans un
; installeur classique : raccourcis menu Demarrer/bureau, desinstalleur,
; entree dans "Applications et fonctionnalites".
;
; Build (depuis une machine Windows avec Inno Setup 6 installe, apres avoir
; genere packaging\dist\LithoShape3D\ via PyInstaller) :
;   iscc packaging\lithoshape3d_installer.iss
;
; La version est passee en ligne de commande par la CI (/DAppVersion=x.y.z)
; pour rester synchronisee avec pyproject.toml sans duplication manuelle.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define AppName "LithoShape3D"
#define AppPublisher "LithoShape3D"
#define AppExeName "LithoShape3D.exe"
#define SourceDir "dist\LithoShape3D"

[Setup]
AppId={{6E2C6C61-6B0E-4C9B-9C2E-3B6C2E9E5C1A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist_installer
OutputBaseFilename=LithoShape3D-Setup-{#AppVersion}
SetupIconFile=icons\lithoshape3d.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
