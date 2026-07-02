# Cria um atalho "Master-Sword" na área de trabalho que já abre o app elevado.
#
# Por que não é um .bat/.lnk pedindo elevação direto no python.exe: o SmartScreen bloqueia
# elevação de binários sem reputação (nosso python.exe do venv é novo/local), sem opção de
# "executar assim mesmo". A saída é elevar um binário confiável (powershell.exe) e deixar
# ele chamar nosso python.exe como processo filho, já dentro da sessão elevada.

$ProjectRoot = $PSScriptRoot
$ShortcutPath = "$env:USERPROFILE\Desktop\Master-Sword.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoLogo -NoProfile -Command `"Set-Location '$ProjectRoot'; & '.\.venv\Scripts\python.exe' main.py`""
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.Description = "Master-Sword - controle de GPU/CPU"
$shortcut.IconLocation = "$ProjectRoot\assets\icon.ico"
$shortcut.WindowStyle = 7
$shortcut.Save()

# .lnk guarda um byte de flags no offset 0x15; bit 0x20 = "roda como administrador"
$bytes = [System.IO.File]::ReadAllBytes($ShortcutPath)
$bytes[0x15] = $bytes[0x15] -bor 0x20
[System.IO.File]::WriteAllBytes($ShortcutPath, $bytes)

Write-Output "Atalho criado em: $ShortcutPath"
