# M4 — Execution runner · Tasks

Order per CLAUDE.md §4: tests first, then rules → service → schemas → router → authz → client →
frontend → E2E → close-out. Decisions D1–D10 in design.md §1 (made by Kiro; user asked to proceed).

## 0. Docs

- [x] 0.1 docs/02 §7.3 + docs/01 BR-10 (D1); docs/02 §7.3 prose + docs/04 §5.5 pseudocode (D2); docs/02 §13.1 unchanged; docs/06 §4.12 attachment entity `test_step_result`; docs/08 TCMS-001 landing (K5).

## 1. Rules (tests first)

- [x] 1.1 Unit tests: roll-up matrix (TCMS-071), finalize problems (TCMS-072/073/075, AC-EXE-01/02/03), text format (TCMS-089), derive_run_status (BR-08), BR-32, duration.
- [x] 1.2 `execution/rules.py`: `compute_final_status`, `finalize_problems`, `derive_run_status`, `executes_as`, `duration_seconds`.

## 2. Attempts backend

- [x] 2.1 API tests `tests/api/test_attempts.py` (R-090…R-100).
- [x] 2.2 Repository + service: start/take over/record/pass remaining/update/finalize/correct/discard; BR-30, BR-32; audit.
- [x] 2.3 Queries + schemas + router (`api/v1/results.py`), `GET /runs/{id}` draft steps + queue, runs list multi-status.
- [x] 2.4 Evidence: `test_step_result` attachment records (records router dispatch).
- [x] 2.5 My Work: `GET /me/work`.
- [x] 2.6 `execution.verify_run_status` job (D10).
- [x] 2.7 Integration: SQL immutability (TCMS-076), concurrency (TCMS-090), AC-EXE-09 timing.
- [x] 2.8 Authz matrix entries; coverage gate.

## 3. Frontend

- [x] 3.1 `make api-client`; hooks in `features/execution/api.ts` (attempt, steps, finalize, discard, my work).
- [x] 3.2 Runner page + route; keyboard; save indicator/retry; paste evidence; result preview; reason dialogs; history.
- [x] 3.3 Cycle detail "Start testing", run panel "Open in runner".
- [x] 3.4 My Work page, landing redirect, sidebar entry.

## 4. E2E

- [x] 4.1 `frontend/e2e/m4.spec.ts`; update TCMS-001 landing in m1 spec.

## 5. Close-out

- [x] 5.1 `make lint test`, coverage gate, `make e2e`, `make schema-check`.
- [x] 5.2 Seed: some SPARK-CY-1 runs executed (passed/failed/blocked) so dashboards and My Work show data.
- [x] 5.3 CHECKLIST M4, known-limitations (remove L21–L23 when done; add D3, D8), local-setup.
- [x] 5.4 Commit, push, PR; report.
