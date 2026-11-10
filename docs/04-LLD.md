# 04 — Low-Level Design

| Field | Value |
| --- | --- |
| Version | 1.0 · 2026-11-03 |
| Depends on | [03 HLD](03-HLD.md), [05 Database](05-Database-Design.md), [06 API](06-API-Specification.md) |
| Audience | Claude Code and the two maintainers |

This document fixes the code-level structure so that generated code is consistent across modules. When adding code, follow the templates here; deviations need an ADR.

---

## 1. Repository layout

```
tcms/
├── CLAUDE.md                     # entry instructions for Claude Code
├── README.md
├── Makefile                      # dev commands (see §2)
├── docker-compose.yml            # local dev
├── docker-compose.prod.yml       # production reference
├── .env.example
├── docs/                         # this specification package
├── backend/
│   ├── pyproject.toml            # uv-managed; ruff, mypy, pytest, import-linter config
│   ├── alembic.ini
│   ├── migrations/               # alembic env + versions/
│   ├── src/tcms/
│   │   ├── main.py               # FastAPI app factory
│   │   ├── cli.py                # `tcms` CLI (migrate, worker, bootstrap, seed, ...)
│   │   ├── core/                 # config, db, security, errors, pagination, permissions, ids, clock, events, uow
│   │   ├── api/                  # routers per module + deps.py
│   │   │   ├── deps.py
│   │   │   └── v1/{auth,organization,projects,folders,test_cases,plans,cycles,runs,results,
│   │   │           defects,requirements,traceability,dashboards,reports,search,saved_views,
│   │   │           comments,attachments,notifications,audit,data_transfers,health}.py
│   │   ├── identity/             # models.py, repository.py, service.py, schemas.py, queries.py, permissions.py
│   │   ├── workspace/
│   │   ├── testdesign/
│   │   ├── planning/
│   │   ├── execution/
│   │   ├── bugs/            # bug links (ADR-023)
│   │   ├── defects/         # unused baseline models
│   │   ├── requirements/
│   │   ├── reporting/            # metrics.py (definitions), queries/*.sql, snapshots.py
│   │   ├── integrations/         # base.py (Connector protocol), registry.py, jira/ (P2), automation/ (P2)
│   │   ├── platform/             # audit, jobs, attachments, comments, notifications, saved_views, data_transfers, email
│   │   └── seed/                 # demo data (SPARK)
│   └── tests/
│       ├── conftest.py           # testcontainers postgres, factories, clients per role
│       ├── factories/
│       ├── unit/                 # pure functions (rollup, coverage rules, transitions)
│       ├── integration/          # service + DB per module
│       ├── api/                  # HTTP tests per router, authz matrix
│       └── contract/             # schemathesis
├── frontend/
│   ├── package.json              # pnpm
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── app/                  # router, providers, layout shell
│   │   ├── api/                  # generated schema.d.ts + client.ts + query keys
│   │   ├── components/ui/        # shadcn components (owned)
│   │   ├── components/common/    # DataTable, StatusBadge, MarkdownEditor, UserPicker, FolderTree, ...
│   │   ├── features/             # one folder per domain: auth, projects, repository, test-cases, plans,
│   │   │                         # cycles, runner, defects, requirements, traceability, dashboards,
│   │   │                         # reports, admin, search, my-work
│   │   ├── hooks/
│   │   ├── lib/                  # format, permissions, keyboard, markdown
│   │   └── styles/
│   └── tests/                    # vitest unit; e2e/ playwright
└── ops/
    ├── caddy/Caddyfile
    ├── backup/                   # pg_dump script + restore runbook
    └── k6/                       # performance scripts
```

## 2. Developer commands (Makefile)

| Command | Does |
| --- | --- |
| `make up` | `docker compose up -d` (db, minio, mailpit, api, worker, web) |
| `make migrate` | `tcms migrate` (alembic upgrade head) |
| `make seed` | Load SPARK demo org/project, users per role (password `Passw0rd!Passw0rd`, MFA off except the Org Admin, who is pre-enrolled with the documented dev-only TOTP secret in docs/ops/local-setup.md; refused in production), 2 releases; later milestones add cases, cycles and results |
| `make test` | Backend pytest + frontend vitest |
| `make e2e` | Playwright against compose stack |
| `make lint` | ruff, mypy, import-linter, eslint, tsc |
| `make api-client` | Export OpenAPI JSON and regenerate `frontend/src/api/schema.d.ts` |
| `make perf` | k6 scenarios against staging-size seed (`make seed-large`) |

## 3. Backend module template

Each domain package contains:

| File | Contents |
| --- | --- |
| `models.py` | SQLAlchemy ORM classes (private to module) |
| `repository.py` | Query functions taking `Session` and `AccessContext`; always tenant-scoped (private) |
| `service.py` | Public use-case functions (the only write entry points) |
| `queries.py` | Public read functions returning Pydantic read models (for other modules and routers) |
| `schemas.py` | Pydantic request/response models |
| `rules.py` | Pure functions for business rules (no DB) — unit-tested exhaustively |
| `events.py` | Domain event dataclasses |
| `errors.py` | Module error codes (subclasses of `DomainError`) |

### 3.1 Core primitives (`tcms.core`)

```python
# core/context.py
@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    is_org_admin: bool
    token_id: UUID | None = None          # set when authenticated by API token
    token_scope: frozenset[str] | None = None

@dataclass
class AccessContext:
    principal: Principal
    project_id: UUID | None
    permissions: frozenset[str]           # effective for project_id (or org-level)
    request_id: str
    ip: str | None
    user_agent: str | None

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionDenied(permission)
```

```python
# core/errors.py
class DomainError(Exception):
    status: int = 400
    code: str = "bad_request"
    def __init__(self, detail: str = "", **extra): ...

class NotFound(DomainError):          status, code = 404, "not_found"
class PermissionDenied(DomainError):  status, code = 403, "permission_denied"
class Conflict(DomainError):          status, code = 409, "conflict"
class StaleRowVersion(Conflict):      code = "stale_row_version"
class RuleViolation(DomainError):     status, code = 422, "rule_violation"
```

Exception handler maps `DomainError` → RFC 9457 problem (see [06 API §3](06-API-Specification.md)).

```python
# core/uow.py — one transaction per request/job
@contextmanager
def unit_of_work(session_factory) -> Iterator[UnitOfWork]:
    session = session_factory()
    uow = UnitOfWork(session)               # collects audit events, domain events, jobs
    try:
        yield uow
        uow.flush_audit()                   # inserts audit_events
        uow.dispatch_in_tx_events()         # handlers that must be consistent
        session.commit()
        uow.after_commit()                  # nothing that can fail the request
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

FastAPI dependency `get_uow` yields a `UnitOfWork` per request; GET routes use a read-only session (`SET TRANSACTION READ ONLY`). Routers take it as `uow: UnitOfWork = Uow` (or `ReadUow`), which are `Depends(get_uow, scope="function")` (`tcms/api/deps.py`): the transaction commits when the route function returns, **before** the response is sent. With the default request scope FastAPI commits after the response, so a client's next request could reach another api replica before the write was committed (found in the M8c load test: read-your-writes failed across replicas).

Two patterns complement it (docs/ops/00-review.md G1, G2):

- **Authentication runs in its own short write transaction** before the route's UoW (session `last_seen_at` touch, API token `last_used_at`, `project.admin_accessed` audit), so GET routes stay read-only.
- **Failures that must leave a trace** (failed sign-in, lockout, wrong MFA code) return `tcms.core.outcome.Outcome.fail(error)` instead of raising; the router lets the UoW commit and then calls `unwrap()`, which raises.

### 3.2 Service function template

```python
# testdesign/service.py
def update_test_case_content(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, cmd: UpdateContentCommand
) -> TestCaseRead:
    case = repo.get_case_for_update(uow.session, ctx, case_id)      # SELECT ... FOR UPDATE, scoped; NotFound if absent
    ctx.require("testcase.edit")
    rules.ensure_editable(case)                                       # archived → RuleViolation
    check_row_version(case.row_version, cmd.row_version)              # StaleRowVersion
    latest = repo.get_version(uow.session, case.latest_version_id)
    new_content = rules.normalize_content(cmd.content)
    if rules.content_hash(new_content) == latest.content_hash:
        return queries.read_case(uow.session, ctx, case_id, version_created=False)
    version = repo.insert_version(uow.session, case, new_content, ctx.principal.user_id, cmd.change_note)
    rules.apply_version_to_status(case, version, project_settings(ctx))   # BR-17 / §5.4
    case.row_version += 1
    uow.audit(ctx, "test_case.version_created", case, changes={"version": [latest.version_no, version.version_no]})
    uow.emit(TestCaseVersionCreated(case.id, version.id))
    return queries.read_case(uow.session, ctx, case_id, version_created=True)
```

Rules every service follows:

1. Load the target with `FOR UPDATE` when changing it (prevents lost updates in concurrent writes).
2. Permission check **after** loading (so non-members get 404, members without permission get 403).
3. Business rules in `rules.py` (pure, testable).
4. Audit via `uow.audit(...)` — never insert into `audit_events` directly.
5. Side effects (email, integration calls) only via `uow.enqueue_job(...)`.
6. Return a read model from `queries`, not ORM objects.

### 3.3 Router template

```python
# api/v1/test_cases.py
router = APIRouter(prefix="/api/v1", tags=["test-cases"])

@router.put("/test-cases/{case_id}/content", response_model=TestCaseRead)
def put_content(
    case_id: UUID,
    body: UpdateContentRequest,
    uow: UnitOfWork = Depends(get_uow),
    ctx: AccessContext = Depends(project_context_from("test_case", "case_id")),
) -> TestCaseRead:
    return service.update_test_case_content(uow, ctx, case_id, body.to_command())
```

`project_context_from(entity_type, path_param)` resolves the entity's `project_id` with a light query (`SELECT project_id, organization_id FROM test_cases WHERE id = :id`), verifies org match and membership (404 otherwise), loads permissions, and builds `AccessContext`.

### 3.4 Repository scoping

```python
class ScopedQuery:
    @staticmethod
    def project(stmt, model, ctx: AccessContext):
        return stmt.where(model.organization_id == ctx.principal.organization_id,
                          model.project_id == ctx.project_id)
```

Every repository function must apply `ScopedQuery.project` (or `.org`). A test (`tests/integration/test_scoping.py`) introspects repository functions with a cross-tenant fixture to ensure no leakage.

### 3.5 Audit recorder

`uow.audit(ctx, action, entity, changes=None, summary=None, extra=None)`:
- builds `audit_events` row: actor from ctx (`user`/`api_token`/`system`), `entity_type` from model `__audit_type__`, `entity_key` from `entity.key` when present, `changes` computed by `diff(old, new)` helpers that redact secrets, `context` = request_id/ip/user_agent/bulk_operation_id.
- Rendering of `summary` sentences happens in `platform/audit/render.py` from `action` + entity + changes.

### 3.6 Human key allocation

```sql
UPDATE key_sequences SET next_value = next_value + 1
WHERE project_id = :pid AND entity = :entity
RETURNING next_value - 1;
```

Row created with `next_value = 1` for each entity when the project is created. Key string built as `f"{project.key}-{PREFIX[entity]}-{n}"` and stored (`key`) alongside `key_num`.

### 3.7 IDs and time

- `tcms.core.ids.new_id()` → UUIDv7 (`uuid_utils.uuid7()`).
- `tcms.core.clock.now()` → timezone-aware UTC; tests freeze it via fixture. Never call `datetime.now()` directly.

## 4. Test design algorithms

### 4.1 Content normalization and hash

- Trim trailing whitespace per line, convert `\r\n` → `\n`, strip leading/trailing blank lines of every Markdown field; empty → `NULL`.
- `content_hash = sha256(canonical_json({format, title, description, preconditions, test_data, expected_result, postconditions, text_body, steps:[{action, expected_result, data}]}))`.

### 4.2 Insert version

1. `version_no = latest.version_no + 1` (`SELECT … FOR UPDATE` on case ensures serial numbering; unique `(test_case_id, version_no)` as backstop).
2. Insert `test_case_versions`, then `test_case_steps` with new UUIDs and `position` 1..n.
3. Carry forward step attachments: for each new step at position p where old step at p exists and has attachments, insert `attachment_links` to the new step (same attachment object).
4. Update case: `latest_version_id`, `title`, `format`, `updated_at/by`, `search` fields.

### 4.3 Status application (`rules.apply_version_to_status`)

```
if not settings.approval_required:
    version.approval_mode = "auto"; version.approved_at = now; version.approved_by = None
    case.approved_version_id = version.id; case.status = (case.status if case.status == "deprecated" else "approved")
else:
    if case.status in ("approved", "deprecated"): case.status = "draft"
    # in_review stays in_review; draft stays draft
```

### 4.4 Approve

```
require testcase.approve
case.status must be in_review (else 409 invalid_status)
version = latest
if version.created_by == user and not settings.allow_self_approval: 403 self_approval_not_allowed
version.approved_by/at = user/now; approval_mode = manual
case.approved_version_id = version.id; case.status = approved
```

Note: `test_case_versions` is immutable except submission and approval columns; the immutability trigger allows `submitted_by`/`submitted_at` to change and `approved_by`, `approved_at`, `approval_mode` to be set once (NULL → value).

## 5. Execution algorithms

### 5.1 Eligible version (BR-03, BR-17)

```
eligible_version(case, settings) =
   None if case.status == "archived"
   None if purpose == "new_cycle" and case.status == "deprecated"
   case.approved_version_id if settings.approval_required else case.latest_version_id
```

### 5.2 Create cycle / add cases

```
for each case_id in selection (deduplicated):
    v = eligible_version(case)
    if v is None: skipped.append((case.key, reason)); continue
    if exists non-superseded run (cycle, case): skipped.append((key, "already_in_cycle")); continue
    insert test_runs(cycle_id, test_case_id, test_case_version_id=v, status='not_run', position=next_pos, assignee_id=default)
audit run.added (one event per run, bulk_operation_id shared)
```

> 500 cases → job `cycle.create_runs`; cycle has `runs_pending = true` until done; UI polls.

### 5.3 Start attempt

```
run = lock run FOR UPDATE
cycle = run.cycle; require cycle.status != closed           # 409 cycle_closed
require run.superseded_by_run_id is null                     # 409 run_superseded
require ctx.require("run.execute"); BR-32 check
draft = find draft for run
if draft: if draft.executed_by == user: return draft
          elif ctx has cycle.manage and body.take_over: draft.executed_by = user; audit result.draft_taken_over; return
          else 409 draft_exists
attempt_no = max(attempt_no)+1
insert test_results(state=draft, executed_by=user, started_at=now, build=cycle.build, environment_id=cycle.environment_id,
                    corrects_result_id=body.corrects_result_id (validate: same run, final))
insert test_step_results for each step of pinned version (status=not_run)
run.status = in_progress; if cycle.status == planned: cycle.status = active (BR-30)
audit result.started
```

### 5.4 Record step

`PATCH /results/{id}/steps/{step_id}`: lock result row (`FOR UPDATE` on `test_results` only), require draft, require executor or cycle.manage, validate (failed → actual_result required **at finalize**, not at each save, so testers can type), update step row (`updated_at/by`). No audit event per step.

### 5.5 Finalize (BR-09) — `execution/rules.py`

```python
def compute_final_status(fmt: str, steps: list[StepStatus], explicit: Outcome | None) -> FinalStatus:
    if fmt == "text":
        if explicit is None: raise RuleViolation("outcome_required")
        return explicit
    if explicit in ("passed", "failed"): raise RuleViolation("outcome_conflicts_with_steps")   # steps decide (K17i)
    if "failed" in steps:
        if explicit is not None: raise RuleViolation("outcome_conflicts_with_steps")           # K17h
        return "failed"
    if "blocked" in steps and explicit in (None, "blocked"): return "blocked"
    if explicit in ("blocked", "skipped", "not_applicable"): return explicit
    if all(s in ("passed", "skipped") for s in steps) and "passed" in steps: return "passed"
    raise RuleViolation("incomplete_attempt")
```

Finalize service:

```
lock result + run
validate: state draft; executor or cycle.manage; failed steps have actual_result (422 actual_result_required, lists step positions);
          reason present for every final blocked/skipped/not_applicable, derived or explicit (K2, 422 reason_required);
          require_bug_link_for_failure: emit ResultFinalizing and dispatch now (bugs: 422 bug_link_required, §6)
status = compute_final_status(...)
result.state = final; result.status = status; result.finished_at = now; result.duration_seconds = body or computed;
result.skipped_steps = count(skipped)
run.status = status; run.latest_result_id = result.id; run.needs_retest = false
audit result.finalized (changes include step statuses summary, status)
emit ResultFinalized
```

After finalize, the immutability trigger forbids changes to the result and its step rows.

### 5.6 Run status when attempts change

`run.status` is maintained by the service, but `rules.derive_run_status(attempts)` exists for verification and is used by a nightly consistency check job (`execution.verify_run_status`) that logs and alerts on mismatches (never silently fixes).

### 5.7 Replace run (BR-05)

```
lock run; require cycle.manage; require run has ≥1 final attempt; cycle not closed; not superseded
v = eligible_version(case); require v != run.version (else 409 already_latest)
new = insert test_runs(... version=v, position=run.position, assignee_id=run.assignee_id, status=not_run)
run.superseded_by_run_id = new.id; run.superseded_at = now
partial unique index (cycle_id, test_case_id) WHERE superseded_by_run_id IS NULL → set old first (same tx; deferrable not needed because update happens before insert)
audit run.replaced
```

Order: generate the new run's UUID, update the old run's `superseded_by_run_id` to it, then insert the new run. This works only because `fk_test_runs_superseded_by_run_id` is DEFERRABLE INITIALLY DEFERRED (checked at commit); the partial unique index forbids inserting the new run first.

## 6. Bug links (ADR-023)

Bugs live in each team's tracker; the `bugs` module stores references (`bug_links`, docs/05 §3.6). It sits beside `defects` (unused) above `execution`.

- `bugs/rules.py` (pure): reference validation (1–100, no spaces) and `reference_norm = upper(trim)`, URL validation (`http`/`https` with a host only), template building (`{ref}` URL-encoded), and the "Copy bug details" Markdown (`bug_report`).
- `bugs/service.py`: `link_to_result` (attempt, run, step, case; draft or final — links are not part of the attempt), `link_to_case`, `update_link`, `remove_link` (creator or `defect.edit`), `request_retest(reference, dry_run)`.
- Retest (BR-21): `request_retest` collects the reference's `run_id`s and calls `execution.service.flag_runs_for_retest`, which sets `needs_retest` on runs that are not superseded and whose cycle is planned or active; audit `bug.retest_requested` with the run ids.
- `require_bug_link_for_failure` (§5.5): `finalize_attempt` emits `ResultFinalizing(ctx, result_id, status)` and dispatches it at once; the bugs handler raises `422 bug_link_required` when the setting is on, the status is `failed` and the attempt has no link.
- Discarding a draft (and closing a cycle with drafts): `DraftDiscarding(ctx, result_id, reason)` is dispatched before the delete; the handler deletes the attempt's links (audited `bug.unlinked`), so the FK on `result_id` holds.

## 7. Requirements coverage (SQL)

Since ADR-024 coverage runs over `requirement_refs` and `requirement_ref_cases`. The SQL lives in `reporting/coverage.py` (reporting reads every module's tables, docs/03 §5); the status rules come from `requirements/rules.py` and the rates from `reporting/metrics.RequirementCoverage` (ADR-013).

```sql
-- scope: a reference is in scope for release :rid when a plan of the release lists it,
-- or a linked case ran in a cycle of the release (M6 Q1 = a). Without a release: every non-archived reference.
SELECT q.id FROM requirement_refs q
WHERE q.project_id = :pid AND q.archived_at IS NULL
  AND (:rid IS NULL
       OR EXISTS (SELECT 1 FROM plan_requirement_refs pr JOIN test_plans p ON p.id = pr.plan_id
                  WHERE pr.ref_id = q.id AND p.release_id = :rid)
       OR EXISTS (SELECT 1 FROM requirement_ref_cases rc
                  JOIN test_runs r ON r.test_case_id = rc.test_case_id
                  JOIN test_cycles c ON c.id = r.cycle_id
                  WHERE rc.ref_id = q.id AND c.release_id = :rid));

-- latest final, non-N/A attempt per linked case among non-superseded runs of the release's cycles
SELECT DISTINCT ON (r.test_case_id) r.test_case_id, tr.status, tr.finished_at, tr.executed_by, r.id, c.key
FROM test_results tr
JOIN test_runs r ON r.id = tr.run_id
JOIN test_cycles c ON c.id = r.cycle_id
WHERE c.project_id = :pid AND (:rid IS NULL OR c.release_id = :rid)
  AND r.superseded_by_run_id IS NULL
  AND tr.state = 'final' AND tr.status <> 'not_applicable'
  AND r.test_case_id = ANY(:case_ids)
ORDER BY r.test_case_id, tr.finished_at DESC, tr.id DESC;
```

Archived cases are left out of the links. Status mapping in Python (`requirements/rules.py::status_in_release`) per [02 §10.5](02-Functional-Specification.md). Rows are sorted in natural order of the reference (SPK-2 before SPK-10); there is no hierarchy. Unit tests cover each branch; `tests/integration/test_coverage_oracle.py` compares the SQL with a pure-Python reference implementation on random fixtures (Hypothesis property test).

Traceability (`GET /requirements/traceability`) adds the bug references per case: for a release, only bug links from runs of that release count; links made directly on the case always count.

## 8. Reporting

- `reporting/metrics.py` defines each metric once (name, SQL fragment, formatter). Dashboards and exports use these definitions only (ADR-013).
- Execution summary query:

```sql
SELECT status, count(*) FROM test_runs r
JOIN test_cycles c ON c.id = r.cycle_id
WHERE c.project_id = :pid AND r.superseded_by_run_id IS NULL
  AND (:release_id IS NULL OR c.release_id = :release_id)
  AND (:cycle_ids IS NULL OR c.id = ANY(:cycle_ids))
GROUP BY status;
```

`ExecutionSummary.from_counts()` computes A, E, rates (returning `None` rather than 0 when the denominator is 0).

- Module filter: `test_cases.folder_id` → ancestor at `report_module_depth` via `folders.path` (materialized path, see [05 §3](05-Database-Design.md)).
- `reporting/queries.py` (M7): one `Scope` (release, cycles, plan, environment, module, tester, date range, tag) and `runs_sql(ctx, scope)`, the "runs in scope" relation (non-superseded runs with their current final attempt) that every dashboard count, readiness rule, snapshot and run-based report is built on. SQL is assembled from fixed fragments; every value is bound.
- Snapshot job `metrics.snapshot` (daily 00:15 UTC; `POST …/metrics/refresh` enqueues today, one per 10 min) writes `metric_snapshots(project_id, release_id NULL|id, cycle_id NULL|id, day, counters jsonb)` for the project, open or recently released releases and open cycles. The state at the end of day D is computed from attempts finished before midnight (latest final attempt per run; runs created later or superseded earlier are left out), so any day can be recomputed and the upsert is idempotent. Counters (ADR-023 replaced the defect counters): `{total, na, passed, failed, blocked, skipped, not_run, in_progress (always 0), executed_on_day, passed_on_day, failed_on_day, blocked_on_day, bug_links_added, bug_refs, failed_without_bug, req_total, req_covered, req_passed, req_failed}`. Trends read snapshots for past days plus today live.
- Caching (M8c, `reporting/cache.py`): at 10× year one the quality dashboard's live "today" counters and its per-release table scan every run of the project, so each api process keeps those two results for 5 minutes (`LIVE_TTL_SECONDS`); the trend's last point and the release table can be up to 5 minutes old, everything else is live. Within one database session `coverage_rows` and `status_counts` are memoised in `session.info` and dropped on the next flush, so a dashboard that asks twice reads once.
- Readiness: `reporting/readiness.py` (ADR-025) — `evaluate(rule, inputs)` is pure; `plan_readiness` / `release_readiness` gather inputs through `queries` and `coverage`. `as_json` is the decision snapshot: `{ready, uses_defaults, evaluated_at, rules: [{type, threshold, params, actual, count, met, note, plan}], plans, summary, coverage, release}`.
- Reports: `reporting/reports.py` declares the six reports (columns, filters, row query) once; JSON, CSV and XLSX use the same rows. `reporting/exports.py`: CSV (BOM) and XLSX (`openpyxl` write-only) writers with formula escaping; > 10,000 rows → `platform/transfers.py` record + job `export.generate`, object under `exports/` in the attachment bucket, `transfers.expire` daily.

## 9. Integrations (P2) — interfaces fixed now

```python
class Connector(Protocol):
    type: ClassVar[str]                                    # "jira_cloud"
    def __init__(self, connection: ConnectionConfig, secrets: ConnectionSecrets): ...
    def test_connection(self) -> ConnectionHealth: ...
    def list_projects(self) -> list[ExternalProject]: ...
    def get_issue(self, key: str) -> ExternalIssue: ...
    def search_issues(self, query: str, cursor: str | None) -> Page[ExternalIssue]: ...
    def create_issue(self, req: CreateExternalIssue) -> ExternalIssue: ...
    def map_status(self, external_status: str) -> StatusCategory: ...
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent | None: ...
```

- `registry.get(connection.type)` returns the class. Connectors are pure HTTP adapters (httpx, timeouts 10 s, retries handled by jobs not inside connectors).
- Jobs: `jira.create_issue(result_id, step_id)` (creates the issue and a bug link), `jira.refresh_issue(link_id)`, `jira.import_requirements(connection_id, project_id)`, `jira.poll(connection_id)`.
- Automation parser interface: `parse(file) -> Iterator[AutomatedTestResult(key, name, status, duration, message, stdout, stderr)]`; JUnit parser uses `defusedxml.ElementTree.iterparse`.

## 10. Platform services

### 10.1 Jobs API

```python
uow.enqueue_job("email.send", payload={...}, run_at=None, dedupe_key=None, max_attempts=5)

@job_handler("email.send")
def send_email(job: Job, uow: UnitOfWork) -> None: ...
```

Retry backoff: `min(2 ** attempts * 30s, 4h)`; after `max_attempts` → `dead`. Handlers must be idempotent (use dedupe keys or check state).

Recurring jobs (`worker.schedule(type, period=, offset=)`) get the dedupe key `schedule:{type}:{period number}`. The unique dedupe index covers only queued and running jobs, so the 30-second scheduler tick also skips a period whose key exists in any state (M8b fix: before, a finished period was enqueued again on every tick).

### 10.2 Attachments

```
upload(ctx, entity_type, entity_id, file):
  require write permission on owning entity (map entity_type → permission)
  check BR-28 (entity mutable), count ≤ 50
  stream to S3 under random key while hashing and counting bytes; abort > limit (413)
  sniff mime from first 8 KB; reject if not allowed (415)
  insert attachments + attachment_links; audit attachment.uploaded
```

Draft-attempt attachments are linked to `test_step_result` rows; on discard, links removed and objects queued for GC.

### 10.2b Administration reads and the retention purge (M8b)

- `platform/audit/queries.events(s, org_id, page, project_id=, filters=)` and `export_events(…, limit=)` serve both audit logs; `AuditFilter` gained `project_id`. The activity feed (`project_activity`) still hides `project.admin_accessed`; the audit logs do not.
- `platform/jobs/admin.py`: `stats`, `jobs`, `job` and `retry(uow, ctx, job_id)` (requires `org.manage`, `409 invalid_status` unless failed or dead, audits `job.retried`, then `queue.retry_dead`). Visibility is `organization_id = :org OR organization_id IS NULL`; rows never carry the payload.
- `workspace/access_review.rows(s, org_id)` joins `identity.queries.org_members` and the new `org_memberships` with the project list; `HEADER`/`KINDS` drive the CSV and XLSX.
- `api/v1/health.run_checks(state)` holds the readiness checks; `/health/ready` and `/organization/system-status` both call it. The version comes from `core/version.py`.
- Retention: `workspace/retention.py` (job `audit.retention`, daily 02:30 UTC) reads each organization's `audit_retention_years`, computes the cutoff as the same calendar day that many years ago, and calls `platform/audit/retention.purge` (batches of 10,000) on a session from the maintenance factory. `tcms worker` configures that factory from `DATABASE_MAINTENANCE_URL` (pool of one); without it the job fails permanently with a message naming the variable. The `audit.purged` record is written with the same maintenance session, so the delete and its record commit together.

### 10.3 Import pipeline

```
upload → data_transfers(kind=import, status=uploaded, file in S3)
dry_run job: parse (openpyxl read_only / csv), apply mapping, build ImportPlan (cases to create/update/unchanged, folders to create, errors)
            store plan summary + errors JSON; status=validated
commit job: re-run validation (data may have changed), then within ONE transaction:
            create folders, allocate keys, insert cases + versions + steps, update existing cases via the same service functions
            (bulk_operation_id = transfer id); status=committed; report CSV to S3
```

Use service functions (not raw inserts) so rules and audit apply; batch flush every 500 cases for memory.

As built (M8a, package `tcms.imports`): `platform/spreadsheets.py` reads CSV/XLSX into sheets (values unescaped, §15.1 of docs/02) and writes exports. `fields.py` holds the field catalog, header synonyms and value parsing. `cases.build_plan(rows, mapping, options, context)` and `refs.build_plan` are pure functions over the rows and a `Context` loaded in one pass (existing keys, folder paths, members); they return the planned rows, row problems and warnings, and are unit-tested without a database. Job `import.validate` stores the summary and the first 1,000 errors on the transfer. Job `import.commit` rebuilds the plan; if it is no longer committable (data changed since the dry run) the transfer goes back to `validated` with the new errors. Otherwise it runs `cases.commit` or `refs.commit` inside `uow.savepoint()`: on any exception the savepoint rolls back the rows, and the audit records, domain events and jobs queued inside it are dropped, so the transfer ends `failed` with nothing imported (AC-IMP-03). On success it stores the report CSV, audits `import.committed` with counts (each case's own audit events carry `bulk_operation_id` = transfer id) and notifies the initiator. Measured: 5,000 cases with 20,000 steps validate in 0.6 s and commit in about 41 s (NFR-PERF-06; docs/ops/performance.md).

### 10.4 Notifications

`notifications` rows created by event handlers; email via `email.send` jobs; templates in `platform/email/templates/*.txt|html` (Jinja2, autoescape).

M7: `platform.notifications.notify` writes the rows and, for `comment.mentioned`, enqueues `notifications.email` in the same transaction. The `tcms.notifications` package (layer of `reporting`) renders a row into `{title, url, project_key}` from its payload and SQL key lookups, sends mention emails (`notifications.email`, template `mention`) and the digest (`notifications.digest`, hourly at :05; a user is due when their local time is 07:xx and `preferences.email.last_digest_on` is not today; template `digest`; dedupe `digest:{user}:{local date}`). `notifications.cleanup` deletes rows older than 180 days (daily 03:30 UTC).

## 11. Frontend architecture

### 11.1 Routing (TanStack Router, file-based)

| Path | Screen ([07 UI](07-UI-UX-Specification.md)) |
| --- | --- |
| `/login`, `/login/mfa`, `/forgot`, `/reset/:token`, `/invite/:token`, `/setup-mfa` | Auth |
| `/` | Redirect to last project or `/my-work` |
| `/my-work` | My Work |
| `/org` | Organization dashboard |
| `/p/:projectKey` | Project dashboard |
| `/p/:projectKey/repository` (`?folder=&case=`) | Repository (case opens in side panel) |
| `/p/:projectKey/cases/:caseKey` (`/versions`, `/history`, `/executions`) | Case detail |
| `/p/:projectKey/plans`, `/plans/:planKey` | Plans |
| `/p/:projectKey/cycles`, `/cycles/:cycleKey` | Cycles |
| `/p/:projectKey/cycles/:cycleKey/run/:runId` | Runner |
| `/p/:projectKey/bugs` | Bugs (linked references, ADR-023) |
| `/p/:projectKey/requirements`, `/requirements/:reqKey` | Requirements |
| `/p/:projectKey/traceability` | RTM |
| `/p/:projectKey/dashboards/quality`, `/reports/:report` | Reporting |
| `/p/:projectKey/releases/:releaseId` | Release + readiness |
| `/p/:projectKey/settings/*` | Project settings |
| `/admin/*` | Organization administration |

URLs use human keys; the client resolves keys via `GET /projects/{pid}/resolve?key=` (cached).

### 11.2 State

- Server state only through TanStack Query; query keys built by helpers in `api/keys.ts` (`keys.testCase(id)`, `keys.cycleRuns(cycleId, filters)`).
- Mutations invalidate precise keys; optimistic updates only for step status in the runner.
- Local UI state with `useState`/`useReducer`; no global store library. Persistent preferences (column layouts, last filters) in `localStorage` via a typed helper.
- Current user, org and permissions from `GET /auth/me` cached at app start; `usePermission("cycle.manage")` hides/disables controls (server still enforces).

### 11.3 API client

`make api-client` generates `schema.d.ts`; `api/client.ts` wraps `openapi-fetch` with: base URL `/api/v1`, `credentials: "include"`, CSRF header from cookie, problem+json → `ApiError {status, code, detail, errors[]}`, 401 → redirect to login with `returnTo`.

### 11.4 Shared components (build first)

| Component | Notes |
| --- | --- |
| `AppShell` | Sidebar, top bar (project switcher, search, notifications, user menu), breadcrumbs |
| `DataTable` | Server pagination/sort/filter, column chooser, row selection incl. "select all matching", sticky header, virtualization > 200 rows, saved views slot |
| `FilterBar` | Chips per filter, typed editors (enum multi-select, user, date range, text) |
| `StatusBadge` | Single source of status → color + icon + label for runs, steps, results, cases, requirements |
| `ProgressBar` | Segmented P/F/B/S/NR with counts on hover and in aria-label |
| `MarkdownEditor` / `MarkdownView` | Textarea + toolbar + preview; paste-image upload; sanitized render |
| `FolderTree` | Virtualized, drag-drop move, counts, keyboard navigation |
| `UserPicker`, `TagInput`, `EntityPicker` | Async search |
| `SidePanel` | Right drawer for detail views with deep link |
| `ConfirmDialog`, `ReasonDialog` | Reason-required confirmations |
| `DiffView` | Field and step diff for versions |
| `KeyboardShortcuts` | Registry + help overlay (`?`) |
| `Metric` | Shows value with numerator/denominator and "—" for undefined |

### 11.5 Runner implementation notes

- Loads `GET /runs/{id}?include=version,draft,history` once; step changes `PATCH` with debounced text saves (600 ms) and immediate status saves.
- Optimistic step status update; on error revert and show inline "not saved — retrying".
- Prefetch the next run in the queue when the current run is ≥ 50% recorded.
- Keyboard handler scoped to the runner; disabled while a text field has focus except `Esc` (leave field) and `Ctrl+Enter`.

## 12. Coding conventions

| Area | Convention |
| --- | --- |
| Python naming | snake_case modules/functions, PascalCase classes, enum values lower_snake |
| Types | No `Any` in services/rules; Pydantic models for every request/response |
| SQL | Lower-case keywords allowed; named parameters; no f-strings in SQL |
| Errors | Raise `DomainError` subclasses with stable `code`; never return error dicts |
| Logging | `structlog`; log events not prose (`log.info("cycle.closed", cycle_id=...)`) |
| Time | `clock.now()` only |
| Enums | Defined once in Python (`StrEnum`) and as PostgreSQL enum types via migrations; exported to OpenAPI |
| Frontend naming | PascalCase components, camelCase hooks (`useCycleRuns`), feature folders own their routes, components, hooks |
| Styling | Tailwind utility classes; design tokens in `styles/tokens.css` (CSS variables for light/dark) |
| Tests | Every BR has a test named `test_br_XX_<description>`; every AC-* has a test referencing its ID in the docstring |
| Commits | Conventional Commits (`feat(execution): finalize attempt rollup`) |
| PR checklist | Tests, migrations reviewed, OpenAPI regenerated, docs updated if behaviour changed |
