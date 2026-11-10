<#
Register (or remove) a Windows Task Scheduler job that runs the ChainGuard pipeline every 30 minutes.

    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1                 # install, every 30 minutes
    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1 -Minutes 60     # another interval
    powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1 -Remove         # uninstall
    schtasks /Run /TN ChainGuardPipeline                                                   # run it right now by hand

The task runs only while you are logged in and the laptop is awake. For something that must not depend on your laptop,
run the same command from cron on a server:  */30 * * * *  cd /path/to/repo && python -m src.run_all --trigger schedule
A database lock means a slow run is never overlapped by the next one, and a manual run never collides with a scheduled one.
#>
param([int]$Minutes = 30, [switch]$Remove, [string]$Python = "")

$TaskName = "ChainGuardPipeline"
$Repo = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    schtasks /Delete /TN $TaskName /F
    exit $LASTEXITCODE
}
if (-not $Python) { $Python = (Get-Command python).Source }
$Log = Join-Path $Repo "pipeline_run.log"
# cmd /c so the output of every run is appended to pipeline_run.log (git-ignored)
$Command = "cmd /c `"cd /d `"$Repo`" && `"$Python`" -m src.run_all --trigger schedule >> `"$Log`" 2>&1`""
schtasks /Create /TN $TaskName /TR $Command /SC MINUTE /MO $Minutes /F
if ($LASTEXITCODE -eq 0) { Write-Host "Installed '$TaskName': every $Minutes minutes. Log: $Log. Remove with -Remove." }
