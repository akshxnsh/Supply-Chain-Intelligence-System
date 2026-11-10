# Running the pipeline (schedule or by hand)

Collection is automatic: Fivetran syncs the six sources (GDELT 30 min, GDACS 3 h, Federal Register 6 h, Open-Meteo 6 h,
PortWatch and ECB daily). Everything after collection is ONE command:

    python -m src.run_all

It runs, in order: **dedupe** (group news into events) -> **reader** (read new/changed items with Gemini) -> **risk** (signals, matching,
loss, confidence, alert levels, close stale alerts) -> **judge** (action + act-by on Notify alerts, Groq). Each step skips work already done,
so a run with nothing new makes no model call (about 20 s, mostly database round trips to Neon).

| how | command |
|---|---|
| once, by hand | `python -m src.run_all` (options: `--skip reader,judge`, `--business demo-business-001`) |
| by hand over HTTP | `POST /api/pipeline/run` (optional `business_id`, `skip=judge`) returns 202 at once; `GET /api/pipeline/status` shows running + recent runs; 409 if a run is already going |
| every 30 minutes, Windows | `powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1` (remove with `-Remove`, run now with `schtasks /Run /TN ChainGuardPipeline`) |
| every 30 minutes, any OS | `python -m src.run_all --every-minutes 30` left running, or cron: `*/30 * * * * cd /repo && python -m src.run_all --trigger schedule` |

Safety: a Postgres advisory lock stops two runs overlapping (a scheduled run and a manual one, two schedulers): the second exits as
`skipped_locked`. A failing step is recorded and the next steps still run (`partial`). Every run is a row in `pipeline_runs`
(trigger, status, per-step result and seconds). The scheduled task only runs while the laptop is on; a server cron job does not
depend on it.
