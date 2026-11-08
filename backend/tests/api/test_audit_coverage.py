"""TCMS-130 (FR-AUD-001): every request that changes a record writes at least one audit event.

Each write route's authz-matrix probe runs as the Org Admin while an engine listener notes which tables
the request's INSERT/UPDATE/DELETE statements touched. A request that changed a record must have audit
events with its `X-Request-ID`, unless the route is in `NOT_AUDITED` with the reason from docs/02 §13.1.
Probes that stop at a business rule or change nothing are counted, not judged; the dedicated tests of
those routes check their events.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Final

import pytest
from sqlalchemy import Engine, event, text

from tests.api.authz_matrix import MATRIX, Fixture
from tests.api.test_authz_matrix import callers, fx  # noqa: F401  (fixtures)
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration

MUTATING: Final = ("POST", "PUT", "PATCH", "DELETE")

# Bookkeeping, not records: session activity, rate limits, replay keys, the queue, the log itself.
IGNORED_TABLES: Final = {
    "sessions",
    "login_attempts",
    "idempotency_keys",
    "jobs",
    "audit_events",
    "notifications",
}

# Record changes that are not audited by design (docs/02 §13.1).
NOT_AUDITED: Final[dict[tuple[str, str], str]] = {
    ("PATCH", "/api/v1/results/{result_id}"): "draft attempt edit; the finalize event stores the outcome",
    ("PATCH", "/api/v1/results/{result_id}/steps/{step_id}"): "draft step edit (docs/02 §13.1)",
    ("POST", "/api/v1/results/{result_id}/steps/bulk"): "draft step edits (docs/02 §13.1)",
}

WRITE_ROUTES = sorted(
    (k for k, e in MATRIX.items() if k[0] in MUTATING and e.probe is not None and e.kind != "public"),
    key=str,
)
_STATEMENT = re.compile(r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+\"?(\w+)", re.I)


@pytest.fixture
def touched(world: World) -> Iterator[set[str]]:
    """Tables changed by the app's statements since the set was last cleared."""
    engine: Engine = world.factory.kw["bind"]
    tables: set[str] = set()

    def after(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        m = _STATEMENT.match(statement)
        if m and (cursor.rowcount or 0) > 0 and m.group(1).lower() not in IGNORED_TABLES:
            tables.add(m.group(1).lower())

    event.listen(engine, "after_cursor_execute", after)
    try:
        yield tables
    finally:
        event.remove(engine, "after_cursor_execute", after)


def test_tcms_130_record_changes_are_audited(
    fx: Fixture,  # noqa: F811
    callers: dict[str, ApiClient],  # noqa: F811
    touched: set[str],
    app_engine: Engine,
) -> None:
    admin = callers["org_admin"]
    changed: list[tuple[str, str]] = []
    missing: list[str] = []
    for route in WRITE_ROUTES:
        entry = MATRIX[route]
        assert entry.probe is not None
        method, url, body = entry.probe(fx)  # probe set-up writes are not part of the request
        touched.clear()
        response = admin.request(method, url, json=body)
        if not 200 <= response.status_code < 300 or not touched:
            continue
        changed.append(route)
        with app_engine.connect() as c:
            n = c.execute(
                text("SELECT count(*) FROM audit_events WHERE context->>'request_id' = :r"),
                {"r": response.headers["X-Request-ID"]},
            ).scalar_one()
        if n == 0 and route not in NOT_AUDITED:
            missing.append(f"{route[0]} {route[1]} changed {sorted(touched)} without an audit event")
    assert not missing, "\n".join(missing)
    assert set(NOT_AUDITED) <= set(WRITE_ROUTES), "NOT_AUDITED lists routes that are not write routes"
    # The probes must exercise a real share of the write API, or the check above means little.
    assert len(changed) >= 40, f"only {len(changed)} of {len(WRITE_ROUTES)} probes changed a record"
