# Performance log

Measurements against the targets of docs/01 §8.2 (NFR-PERF). Add a row per measurement; keep old rows.

## How to measure the dashboards (M7)

```
# a separate database so the dev data is untouched
docker compose exec -T db psql -U postgres -c "CREATE DATABASE tcms_large OWNER tcms_owner"
U=postgresql+psycopg://tcms_app:$TCMS_DB_APP_PASSWORD@db:5432/tcms_large
docker compose run --rm -e DATABASE_URL=$U \
  -e DATABASE_MAINTENANCE_URL=postgresql+psycopg://tcms_owner:$TCMS_DB_OWNER_PASSWORD@db:5432/tcms_large migrate
docker compose run --rm -e DATABASE_URL=$U api tcms seed --profile large     # about 15 s
docker compose run --rm -e DATABASE_URL=$U -e LOG_LEVEL=WARNING api tcms seed-timing
```

`tcms seed-timing` calls each endpoint function the API serves (same code and SQL, no HTTP or JSON
encoding) five times as SPARK's QA Manager and prints the median and the worst time. Network and
rendering add little to these numbers; the k6 run in M8 measures end to end.

## 2026-11-06 — M7a, `large` seed (twice year one), Apple Silicon, Docker Desktop

Data: 20,000 cases, 1,220 folders, 20 releases, 400 cycles, 100,000 runs, 97,000 attempts, 4,000 bug
links, 1,000 requirement references (see known limitation L43 for why not 10×).

| Screen / endpoint | Median | Worst | Target |
| --- | --- | --- | --- |
| Overview (manager dashboard), active release | 258 ms | 322 ms | < 2 s (NFR-PERF-04) |
| Overview, whole project | 328 ms | 410 ms | < 2 s |
| Quality dashboard, 30 days | 914 ms | 1,066 ms | < 2 s |
| Release readiness | 103 ms | 154 ms | < 2 s |
| Releases page (20 releases) | 572 ms | 614 ms | < 2 s |
| Traceability, active release | 534 ms | 675 ms | < 2 s |
| Report: cycle execution, page 1 | 56 ms | 62 ms | < 300 ms (NFR-PERF-01) |
| Report: results history, page 1 | 115 ms | 125 ms | < 300 ms |
| Report: case inventory, page 1 | 585 ms | 591 ms | < 300 ms — **over** (fixed, see below) |
| Report: tester activity, page 1 | 183 ms | 219 ms | < 300 ms |
| Execution summary, project | 26 ms | 30 ms | < 300 ms |

The case inventory computed every case's latest result before paging. It now pages the cases first and
looks up the latest result, tags and references for that page only; the count runs without the lookups.
Rerun after the change (same data):

| Screen / endpoint | Median | Worst |
| --- | --- | --- |
| Overview, active release | 267 ms | 565 ms |
| Overview, whole project | 304 ms | 355 ms |
| Quality dashboard, 30 days | 849 ms | 1,058 ms |
| Release readiness | 98 ms | 136 ms |
| Releases page | 540 ms | 545 ms |
| Traceability, active release | 482 ms | 515 ms |
| Report: cycle execution, page 1 | 48 ms | 91 ms |
| Report: results history, page 1 | 105 ms | 114 ms |
| Report: case inventory, page 1 | 6 ms | 8 ms |
| Report: tester activity, page 1 | 162 ms | 163 ms |
| Execution summary, project | 26 ms | 26 ms |

## 2026-11-07 — M8a, import of 5,000 cases (NFR-PERF-06, P5), Apple Silicon, Docker Desktop

Measured by `test_nfr_perf_06_import_5000_cases_with_20000_steps`
(`uv run pytest -m timing tests/api/test_imports.py`): an XLSX with 5,000 cases, 20,000 steps and 160
new folders (20 areas with 7 modules each), imported into an empty project through the API and the job runner.

| Step | Time | Target |
| --- | --- | --- |
| Dry run (`import.validate`) | 0.6 s | — |
| Commit (`import.commit`, one transaction) | 40.4 s | — |
| Dry run + commit | 41.0 s | < 2 min (NFR-PERF-06, US-150) |

The commit writes each case through the test design service, so rules, versions and audit apply to every
case. While it runs, the project's case key sequence stays locked (known limitation L53).

## How to run the load tests (M8c, docs/08 §9, TCMS-142)

The k6 scripts in `perf/` run against the production stack (Caddy, API replicas, worker) loaded with the
`xlarge` seed: 100,000 cases, 500,000 runs and attempts, 20,000 bug links, 5,000 requirement references,
1,220 folders (about 50 s to load).

```bash
cd deploy
./make-secrets.sh                               # once
cp local.env /tmp/perf.env                      # then add: RATE_LIMIT_AUTH_PER_MIN=1000, API_REPLICAS=8,
                                                #   PG_SHARED_BUFFERS=1GB, PG_EFFECTIVE_CACHE_SIZE=3GB
alias perf-stack='docker compose -f docker-compose.prod.yml -f docker-compose.local.yml --env-file /tmp/perf.env'
perf-stack up -d --build && perf-stack run --rm api tcms seed --profile xlarge
cd .. && docker run --rm --network container:assay-prod-caddy-1 -v "$PWD/perf:/perf:ro" \
  -e DURATION=5m grafana/k6:latest run /perf/p1-browse.js        # p2 … p6 the same way
```

Unset `TCMS_*` variables exported by your shell first (they override the env file), stop the development stack
(ports 80/443), and on a laptop run k6 under `caffeinate -dims` so the machine does not sleep. Each VU signs in
once and keeps its session like a browser tab; the three seed testers share the VUs, so the auth limit is raised
for the run. For P4 read `docker stats` after a 3-minute warm-up and again at the end.

## 2026-11-08 … 11-10 — M8c, `xlarge` seed (10× year one), MacBook Pro M4 Pro

Machine: 12 CPU cores, Docker Desktop VM with 8 GB RAM; stack with 8 API replicas (one process each),
PostgreSQL `shared_buffers` 1 GB. This is **not** the 4 vCPU / 8 GB production host of docs/01 §8.2 and the
numbers do not transfer to it; the pilot host is measured in M9 (known limitation L60).

| Scenario | Load | Result | Target | Verdict |
| --- | --- | --- | --- | --- |
| P1 Browse | 30 VUs, 5 min | list p95 73 ms, tree p95 147 ms (1,220 folders), search p95 226 ms, 0 errors | p95 < 300 ms; tree < 1 s; search < 500 ms | Pass |
| P2 Execution | 50 VUs × 3 runs of 10 steps, 2 s think time | step save p95 180 ms; 150 of 150 runs finished with exactly one final result; 0 errors. Start attempt p95 1.17 s, finish p95 558 ms | step save p95 < 200 ms (NFR-PERF-03); 0 errors; no lost updates | Pass (start/finish over the script's own 300 ms; L59) |
| P3 Dashboards | 10 VUs, 3 min | manager p95 2.0 s, quality p95 0.46 s, traceability (5,000 references) p95 1.73 s | p95 < 2 s (NFR-PERF-04) | Pass, manager at the limit |
| P4 Mixed soak | 35 browse + 15 dashboard VUs, 23 min | 88,779 requests, 0 failed (0.00 %), Caddy logged only 200s. API memory after warm-up 2,177 MB (8 replicas), at the end 2,179 MB (+0.1 %); PostgreSQL 2.02 → 1.97 GB. Under this mix: list p95 538 ms, manager p95 9.8 s | error rate < 0.1 %; memory growth < 10 % | Pass on errors and memory; latency over target under mixed load (L60) |
| P5 Background | import 5,000 cases / 20,000 steps and export while 10 VUs browse | import 56.9 s; export of 110,580 result rows 71.8 s; browse p95 173 ms during both | import < 2 min; export completes; browse p95 < 300 ms | Pass |
| P6 Cycle creation | one cycle from a 5,000-case area | 5,000 runs in 2.2–2.9 s | < 60 s | Pass |
| Tree, 2,000 folders (US-043, L14) | `GET /projects/{id}/folders`, 20 calls, dev stack | median 30 ms, p95 93 ms, 452 KB | < 1 s | Pass (API; browser rendering not timed) |

P4 was run three times. Run 1 lost one API replica to the kernel's out-of-memory killer (the Docker VM was full
with `shared_buffers` at 2 GB); run 2 used the old script, which signed in again on every iteration and filled
Caddy's log with 401 and 429 answers that k6 did not count. Run 3 (above) fixed both.

Fixes made while measuring (all in the M8c branch):

- **One process per API replica, `least_conn` in Caddy.** Four gunicorn workers in one container did not share the
  load: one worker's event loop accepted most connections while the others idled. Active health checks took a
  busy replica out of rotation for up to a minute; passive checks only now.
- **Keep-alive.** gunicorn keeps idle connections 75 s, Caddy 60 s, so Caddy never sends on a connection gunicorn
  has just closed (the cause of sporadic 502s).
- **Commit before the response** (`Depends(get_uow, scope="function")`, docs/04 §3.1). FastAPI's default request
  scope committed after the response was sent, so a client's next request could reach another replica before
  its write was visible.
- **psycopg's C implementation** (`psycopg-c`, built in the image) instead of the pure-Python one.
- **Traceability**: bug links for all cases of a release in chunks of 5,000 ids instead of one query per case.
- **Folder tree**: a column-only query instead of loading ORM objects.
- **Quality dashboard**: today's live counters and the release table cached for 5 minutes per process; coverage
  and status counts reused within a request (docs/04 §8).
- **Starting an attempt** takes a shared lock on the cycle (an exclusive one only when it activates a planned
  cycle), so testers no longer queue behind each other.
