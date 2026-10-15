$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path $PSScriptRoot -Parent
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $PSScriptRoot 'start.ps1')) -WorkingDirectory $projectDirectory
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Yuanfuliao-Web' -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description 'Yuanfuliao LAN web server and local database' -Force | Select-Object TaskName, State
Start-ScheduledTask -TaskName 'Yuanfuliao-Web'
