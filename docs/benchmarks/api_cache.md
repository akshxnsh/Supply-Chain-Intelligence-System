# API response times with and without the Redis cache (2026-11-10T19:14:43+00:00)

- uvicorn x1 on localhost, sequential keep-alive requests; DB = DATABASE_URL (Neon Singapore from this laptop), Redis = local Docker
- Database: PostgreSQL 18.6 (ac70818) on a
- A = no cache, old pool check; B = no cache, new pool check; C = Redis cache (hits after the first request)

| endpoint | A p50 / p95 (ms) | B p50 / p95 (ms) | C p50 / p95 (ms) | C vs A (p50) | C vs B (p50) |
|---|---:|---:|---:|---:|---:|
| suppliers | 382.9 / 413.6 | 321.0 / 415.2 | 5.1 / 7.2 | 75x faster | 63x faster |
| alerts (legacy table) | 383.8 / 483.6 | 318.5 / 402.2 | 5.3 / 6.7 | 72x faster | 60x faster |
| risk alerts (new) | 403.6 / 469.8 | 323.8 / 406.5 | 5.0 / 7.8 | 81x faster | 65x faster |
| freshness (6 queries) | 439.3 / 775.2 | 355.4 / 644.4 | 4.5 / 6.8 | 98x faster | 79x faster |

Concurrent (8 threads x 15 requests, mixed endpoints):

| config | requests/second | p50 ms | p95 ms |
|---|---:|---:|---:|
| A_no_cache_old_pool_check | 18.0 | 397.3 | 527.7 |
| B_no_cache_new_pool_check | 24.3 | 304.2 | 413.9 |
| C_redis_cache | 384.2 | 17.6 | 44.5 |
