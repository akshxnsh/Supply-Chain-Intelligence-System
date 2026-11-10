<#
Register (or remove) a Windows Task Scheduler job that runs the ChainGuard pipeline every 30 minutes.

    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1                 # install, every 30 minutes
    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1 -Minutes 60     # another interval
    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1 -Remove         # uninstall
    Start-ScheduledTask -TaskName ChainGuardPipeline                                       # run it right now by hand

Settings chosen on purpose: it also runs on battery (a laptop default would silently skip every run), it catches up a missed run
after sleep (StartWhenAvailable), and a run still going when the next one is due is not doubled up (IgnoreNew; the pipeline
also has its own database lock). It only runs while you are logged in and the laptop is awake: for something that must not depend on
your laptop run the same command from cron on a server:  */30 * * * *  cd /repo && python -m src.run_all --trigger schedule
#>
param([int]$Minutes = 30, [switch]$Remove, [string]$Python = "")

$TaskName = "ChainGuardPipeline"
$Repo = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
    exit 0
}
if (-not $Python) { $Python = (Get-Command python).Source }
$Log = Join-Path $Repo "pipeline_run.log"
# A generated runner (absolute python path, because a scheduled task may not have your PATH); output is appended to pipeline_run.log
$Runner = Join-Path $PSScriptRoot "run_pipeline.bat"
@(
    "@echo off",
    "cd /d `"$Repo`"",
    "`"$Python`" -m src.run_all --trigger schedule >> `"$Log`" 2>&1"
) | Set-Content -Path $Runner -Encoding ASCII

$action = New-ScheduledTaskAction -Execute $Runner
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "ChainGuard: group news, read new items, score risk, judge alerts (python -m src.run_all)" -Force | Out-Null
Write-Host "Installed '$TaskName': every $Minutes minutes via $Runner. Log: $Log. Remove with -Remove."
