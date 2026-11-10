"""Measure API response times with and without the Redis cache (and with the old vs new connection-pool check).

Starts the real FastAPI app with uvicorn (one process) three times and calls it over HTTP on localhost:

  A  no cache, pool checks every connection on every query (the old behaviour: DB_CHECK_AFTER_IDLE_S=0)
  B  no cache, pool trusts connections verified in the last 30 s (new default)
  C  Redis cache on (new default)

Per endpoint: N sequential requests (after warm-up) -> p50 / p95 / p99 / mean; then a small concurrent phase for requests/second.
The database is whatever DATABASE_URL points at (Neon in Singapore from this laptop = the realistic, slow case); Redis is REDIS_URL.

    python -m scripts.benchmark_api            # writes docs/benchmarks/api_cache.json and .md
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "benchmarks"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
ENDPOINTS = [  # (label, path, sequential requests)
    ("suppliers", "/api/suppliers?business_id=demo-business-001", 60),
    ("alerts (legacy table)", "/api/alerts?business_id=demo-business-001", 60),
    ("risk alerts (new)", "/api/risk/alerts?business_id=demo-business-001&limit=20", 60),
    ("freshness (6 queries)", "/api/freshness", 20),
]
CONFIGS = {
    "A_no_cache_old_pool_check": {"API_CACHE": "0", "DB_CHECK_AFTER_IDLE_S": "0"},
    "B_no_cache_new_pool_check": {"API_CACHE": "0", "DB_CHECK_AFTER_IDLE_S": "30"},
    "C_redis_cache": {"API_CACHE": "1", "DB_CHECK_AFTER_IDLE_S": "30"},
}


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(p / 100 * len(s) + 0.5)) - 1))]


def start_server(extra_env: dict) -> subprocess.Popen:
    env = {**os.environ, **extra_env, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.dashboard.api:app", "--port", str(PORT), "--log-level", "warning"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if requests.get(f"{BASE}/api/businesses", timeout=2).ok:
                return proc
        except requests.RequestException:
            time.sleep(1)
    proc.kill()
    raise RuntimeError("server did not start")


def clear_cache() -> None:
    url = dotenv_values(ROOT / ".env").get("REDIS_URL")
    if not url:
        return
    import redis

    r = redis.Redis.from_url(url, decode_responses=True)
    for k in r.scan_iter(match="chainguard:api:*"):
        r.delete(k)


def timed_get(session: requests.Session, path: str) -> tuple[float, str]:
    t = time.perf_counter()
    r = session.get(BASE + path, timeout=60)
    ms = (time.perf_counter() - t) * 1000
    r.raise_for_status()
    return ms, r.headers.get("x-cache", "-")


def run_config(name: str, env: dict) -> dict:
    clear_cache()
    proc = start_server(env)
    try:
        s = requests.Session()
        result: dict = {"env": env, "endpoints": {}}
        for label, path, n in ENDPOINTS:
            first_ms, first_state = timed_get(s, path)          # first request: always cold
            times, states = [], {}
            for _ in range(n):
                ms, state = timed_get(s, path)
                times.append(ms)
                states[state] = states.get(state, 0) + 1
            result["endpoints"][label] = {
                "first_request_ms": round(first_ms, 1), "first_x_cache": first_state, "n": n, "x_cache_counts": states,
                "p50_ms": round(pct(times, 50), 1), "p95_ms": round(pct(times, 95), 1), "p99_ms": round(pct(times, 99), 1),
                "mean_ms": round(statistics.mean(times), 1), "min_ms": round(min(times), 1), "max_ms": round(max(times), 1)}
            print(f"[{name}] {label:24} p50 {result['endpoints'][label]['p50_ms']:8.1f} ms  p95 {result['endpoints'][label]['p95_ms']:8.1f} ms  {states}", flush=True)

        # concurrent phase: 8 threads x 15 requests, mixed endpoints (no freshness: it is a slow multi-query call)
        paths = [p for l, p, _ in ENDPOINTS if not l.startswith("freshness")]
        done, lock = [], threading.Lock()

        def worker():
            sess = requests.Session()
            for i in range(15):
                ms, _ = timed_get(sess, paths[i % len(paths)])
                with lock:
                    done.append(ms)

        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        wall = time.perf_counter() - t0
        result["concurrent_8_threads"] = {"requests": len(done), "seconds": round(wall, 2), "requests_per_second": round(len(done) / wall, 1),
                                          "p50_ms": round(pct(done, 50), 1), "p95_ms": round(pct(done, 95), 1)}
        print(f"[{name}] concurrent: {result['concurrent_8_threads']}", flush=True)
        try:
            result["cache_stats"] = requests.get(f"{BASE}/api/cache/stats", timeout=5).json()
        except requests.RequestException:
            pass
        return result
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    results = {name: run_config(name, env) for name, env in CONFIGS.items()}
    ver = None
    try:
        from src.ingestion.db import run_query
        ver = run_query("select version() as v")[0]["v"][:30]
    except Exception:  # noqa: BLE001
        pass
    report = {"measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "database": ver,
              "setup": "uvicorn x1 on localhost, sequential keep-alive requests; DB = DATABASE_URL (Neon Singapore from this laptop), Redis = local Docker",
              "configs": results}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api_cache.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    lines = [f"# API response times with and without the Redis cache ({report['measured_at']})", "",
             f"- {report['setup']}", f"- Database: {ver}", "- A = no cache, old pool check; B = no cache, new pool check; C = Redis cache (hits after the first request)", "",
             "| endpoint | A p50 / p95 (ms) | B p50 / p95 (ms) | C p50 / p95 (ms) | C vs A (p50) | C vs B (p50) |", "|---|---:|---:|---:|---:|---:|"]
    for label, _, _ in ENDPOINTS:
        a, b, c = (results[k]["endpoints"][label] for k in CONFIGS)
        lines.append(f"| {label} | {a['p50_ms']} / {a['p95_ms']} | {b['p50_ms']} / {b['p95_ms']} | {c['p50_ms']} / {c['p95_ms']} | "
                     f"{a['p50_ms'] / c['p50_ms']:.0f}x faster | {b['p50_ms'] / c['p50_ms']:.0f}x faster |")
    lines += ["", "Concurrent (8 threads x 15 requests, mixed endpoints):", "", "| config | requests/second | p50 ms | p95 ms |", "|---|---:|---:|---:|"]
    for k in CONFIGS:
        cc = results[k]["concurrent_8_threads"]
        lines.append(f"| {k} | {cc['requests_per_second']} | {cc['p50_ms']} | {cc['p95_ms']} |")
    (OUT / "api_cache.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
