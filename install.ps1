# Instala o Master-Sword: tarefa agendada elevada + atalho na área de trabalho. Rodar uma vez.
#
# Por que tarefa agendada: o app precisa de admin (lock de clock da GPU, sensores, EC). Elevar o
# python.exe do venv direto é barrado pelo SmartScreen, e o atalho antigo (powershell elevado
# chamando o python) deixava uma janela de console aberta. A tarefa com "privilégios mais altos"
# sobe o pythonw.exe (sem console) já elevado, sem UAC a cada abertura. O atalho roda o pythonw
# SEM elevação, e o próprio main.pyw dispara a tarefa.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$Main = Join-Path $ProjectRoot "main.pyw"
if (-not (Test-Path $Pythonw)) { throw "Não achei $Pythonw — crie o venv primeiro (ver README)." }

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Main`"" -WorkingDirectory $ProjectRoot
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances Parallel
Register-ScheduledTask -TaskName "Master-Sword" -Action $action -Principal $taskPrincipal `
    -Settings $settings -Force | Out-Null

$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Master-Sword.lnk"
if (Test-Path $ShortcutPath) { Remove-Item $ShortcutPath }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $Pythonw
$shortcut.Arguments = "`"$Main`""
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.Description = "Master-Sword - controle de GPU/CPU"
$shortcut.IconLocation = "$ProjectRoot\assets\icon.ico"
$shortcut.Save()

Write-Output "Tarefa 'Master-Sword' criada e atalho em: $ShortcutPath"
Start-Sleep -Seconds 2
