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
