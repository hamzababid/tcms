"""Seed steps for local development and E2E (docs/04 §2, docs/08 §3). Written through services only.

Credentials are documented in docs/ops/local-setup.md. They are for local machines only; the dev TOTP
secret is refused in production (`enroll_mfa_with_secret`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from tcms.core.config import get_settings
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.db import app_engine, session_factory
from tcms.core.enums import ReleaseStatus
from tcms.core.permissions import RoleCode
from tcms.core.uow import unit_of_work
from tcms.identity import queries as identity_queries
from tcms.identity import service as identity
from tcms.seed import step
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace

SEED_PASSWORD = "Passw0rd!Passw0rd"  # noqa: S105 — documented local seed credential
DEV_TOTP_SECRET = "ASSAYLOCALDEVTOTPSECRETONLY23456"  # noqa: S105 — documented local-only MFA secret
ORG_SLUG = "acme"


@dataclass(frozen=True)
class Person:
    name: str
    email: str
    role: RoleCode


TEAM = (
    Person("Ayesha Raza", "ayesha@acme.test", RoleCode.qa_manager),
    Person("Bilal Khan", "bilal@acme.test", RoleCode.qa_lead),
    Person("Sana Malik", "sana@acme.test", RoleCode.qa_engineer),
    Person("Omar Farooq", "omar@acme.test", RoleCode.developer),
    Person("Hira Siddiqui", "hira@acme.test", RoleCode.pm_ba),
    Person("Faisal Ahmed", "faisal@acme.test", RoleCode.viewer),
)
ADMIN = Person("Zain Ali", "zain@acme.test", RoleCode.qa_manager)
META = RequestMeta("seed")


def _ctx(
    org_id: UUID, user_id: UUID, *, project_id: UUID | None = None, perms: frozenset[str] = frozenset()
) -> AccessContext:
    return AccessContext.for_principal(
        Principal(user_id, org_id, True, display_name=ADMIN.name),
        META,
        project_id=project_id,
        permissions=perms,
    )


def _project(
    factory: object, org_id: UUID, admin_id: UUID, key: str, name: str, users: dict[str, UUID]
) -> str:
    with unit_of_work(factory) as uow:  # type: ignore[arg-type]
        policy = workspace_queries.org_policy(uow.session, org_id)
        p = workspace.create_project(
            uow,
            _ctx(org_id, admin_id, perms=frozenset({"project.create"})),
            key=key,
            name=name,
            description=None,
            policy=policy,
        )
        pctx = _ctx(
            org_id,
            admin_id,
            project_id=p.id,
            perms=frozenset({"project.members.manage", "project.configure", "release.manage"}),
        )
        pctx.project_status = "active"
        for person in TEAM:
            identity.add_member(uow, pctx, user_id=users[person.email], role_code=person.role.value)
        for env in ("Dev", "UAT"):
            workspace.create_environment(uow, pctx, name=env, description=None)
        current = workspace.create_release(
            uow,
            pctx,
            name=f"{key} v2.5",
            description="Regression and release validation",
            start_date=date(2026, 11, 3),
            target_date=date(2026, 11, 14),
        )
        workspace.update_release(
            uow, pctx, current.id, row_version=current.row_version, fields={"status": ReleaseStatus.active}
        )
        workspace.create_release(
            uow,
            pctx,
            name=f"{key} v2.6",
            description=None,
            start_date=date(2026, 12, 1),
            target_date=date(2026, 12, 19),
        )
    return key


def _seed(profile: str) -> str:
    settings = get_settings()
    factory = session_factory(app_engine(settings))
    with factory() as s:
        if workspace_queries.organization_by_slug(s, ORG_SLUG) is not None:
            return "organization 'acme' already exists — nothing to do"
    with unit_of_work(factory) as uow:
        org = workspace.create_organization(uow, name="ACME Energy", slug=ORG_SLUG)
        invites = {
            ADMIN.email: identity.bootstrap_admin_invitation(
                uow, settings, organization_id=org.id, email=ADMIN.email
            )
        }
        org_id = org.id
    users: dict[str, UUID] = {}
    for person in (ADMIN, *TEAM):
        with unit_of_work(factory) as uow:
            if person is not ADMIN:
                ctx = _ctx(org_id, users[ADMIN.email], perms=frozenset({"org.users.manage"}))
                invites[person.email] = identity.create_invitation(uow, settings, ctx, email=person.email)
        token = invites[person.email].accept_url.rsplit("/", 1)[1]
        with unit_of_work(factory) as uow:
            accepted = identity.accept_invitation(
                uow,
                token=token,
                display_name=person.name,
                password=SEED_PASSWORD,
                time_zone="Asia/Karachi",
                meta=META,
                policy_for=lambda o: workspace_queries.org_policy(uow.session, o),
            )
        users[person.email] = accepted.user_id
    with unit_of_work(factory) as uow:
        identity.enroll_mfa_with_secret(uow, settings, _ctx(org_id, users[ADMIN.email]), DEV_TOTP_SECRET)
    keys = [_project(factory, org_id, users[ADMIN.email], "SPARK", "SPARK Platform", users)]
    if profile == "e2e":
        keys.append(_project(factory, org_id, users[ADMIN.email], "HELIOS", "HELIOS Analytics", users))
    return f"ACME Energy with {len(users)} users and projects {', '.join(keys)}"


@step("organization, users and projects", profiles=("dev", "e2e"))
def seed_workspace(profile: str) -> str:
    return _seed(profile)


# -- repository (M2) ------------------------------------------------------------------------------

Steps = tuple[tuple[str, str], ...]

# folder path → cases (title, priority, tags, steps). Realistic SPARK content for local demos.
REPOSITORY: dict[tuple[str, ...], tuple[tuple[str, str, tuple[str, ...], Steps], ...]] = {
    ("Web Application",): (),
    ("Web Application", "Authentication"): (),
    ("Web Application", "Authentication", "Login"): (
        (
            "Login with valid credentials",
            "high",
            ("smoke", "regression"),
            (
                ("Open the sign-in page", "The sign-in form is displayed"),
                (
                    "Enter a valid email and password and select **Sign in**",
                    "The Energy Dashboard loads within 3 s",
                ),
            ),
        ),
        (
            "Login with wrong password shows a generic error",
            "high",
            ("regression",),
            (
                ("Enter a valid email and a wrong password", "“Email or password is incorrect” is shown"),
                ("Check the email field", "The email is kept; the password is cleared"),
            ),
        ),
        (
            "Account locks after five failed attempts",
            "critical",
            ("regression", "security"),
            (
                ("Fail sign-in five times within 15 minutes", "The fifth attempt shows the lockout message"),
                ("Try the correct password", "Sign-in is refused until the lockout ends"),
            ),
        ),
        (
            "Session expires after inactivity",
            "medium",
            ("regression",),
            (
                ("Sign in and stay idle for the configured timeout", "The next action returns to sign-in"),
                ("Sign in again", "The user returns to the page they were on"),
            ),
        ),
    ),
    ("Web Application", "Authentication", "Password Reset"): (
        (
            "Request a password reset link",
            "high",
            ("smoke",),
            (
                (
                    "Select **Forgot password** and enter a registered email",
                    "A confirmation message is shown",
                ),
                ("Open the email", "It contains a single-use link valid for 60 minutes"),
            ),
        ),
        (
            "Reset link cannot be reused",
            "medium",
            ("security",),
            (
                ("Reset the password with the link", "The new password works"),
                ("Open the same link again", "“This link is no longer valid” is shown"),
            ),
        ),
    ),
    ("Web Application", "Dashboard"): (
        (
            "Consumption chart shows the last 30 days",
            "high",
            ("smoke", "regression"),
            (
                ("Open the Energy Dashboard for a site with readings", "The chart shows 30 daily bars"),
                ("Hover a bar", "The tooltip shows date, kWh and cost"),
            ),
        ),
        (
            "Dashboard handles a site without readings",
            "low",
            (),
            (("Open the dashboard for a new site", "An empty state explains that no readings exist yet"),),
        ),
    ),
    ("Backend Services",): (),
    ("Backend Services", "Meter Readings API"): (
        (
            "POST /readings stores a valid batch",
            "critical",
            ("api", "smoke"),
            (
                ("Send a batch of 100 readings with a valid token", "201 with the stored count"),
                ("GET the readings for the meter", "All 100 readings are returned in order"),
            ),
        ),
        (
            "POST /readings rejects duplicate timestamps",
            "high",
            ("api", "regression"),
            (("Send two readings with the same meter and timestamp", "422 with a duplicate_reading error"),),
        ),
    ),
    ("Data Integration",): (
        (
            "Nightly import reconciles meter totals",
            "medium",
            ("regression",),
            (
                ("Run the nightly import for a test tenant", "The job finishes without errors"),
                ("Compare daily totals with the source export", "Totals match to 0.01 kWh"),
            ),
        ),
    ),
}


@step("SPARK repository: folders and test cases", profiles=("dev",))
def seed_repository(profile: str) -> str:
    from tcms.core.enums import CaseFormat, PriorityLevel
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.testdesign import queries as td_queries
    from tcms.testdesign import rules as td_rules
    from tcms.testdesign import service as testdesign

    del profile
    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        org = workspace_queries.organization_by_slug(s, ORG_SLUG)
        if org is None:
            return "no organization — run the workspace step first"
        spark = next(
            (p for p in workspace_queries.projects(s, org.id, ids=None, status=None) if p.key == "SPARK"),
            None,
        )
        if spark is None:
            return "no SPARK project"
        author = next(
            (
                m.user.id
                for m in identity_queries.project_members(s, org.id, spark.id)
                if m.user.email == "sana@acme.test"
            ),
            None,
        )
        if author is None:
            return "Sana is not a SPARK member"
    ctx = AccessContext.for_principal(
        Principal(author, org.id, False, display_name="Sana Malik"),
        META,
        project_id=spark.id,
        permissions=PROJECT_PERMISSIONS,
    )
    ctx.project_status = "active"
    with factory() as s:
        if td_queries.folder_tree(s, ctx, include_archived=True):
            return "SPARK already has folders — nothing to do"
    folder_ids: dict[tuple[str, ...], UUID] = {}
    n_cases = 0
    for path, cases in REPOSITORY.items():
        with unit_of_work(factory) as uow:
            f = testdesign.create_folder(
                uow, ctx, name=path[-1], parent_id=folder_ids.get(path[:-1]), description=None
            )
            folder_ids[path] = f.id
            for title, priority, tags, steps in cases:
                testdesign.create_case(
                    uow,
                    ctx,
                    content=td_rules.Content(
                        format=CaseFormat.steps,
                        title=title,
                        steps=tuple(td_rules.StepContent(a, e, None) for a, e in steps),
                    ),
                    meta=testdesign.CaseMetadata(
                        folder_id=f.id, priority=PriorityLevel(priority), tags=list(tags)
                    ),
                )
                n_cases += 1
    # One case with history: v2 clarifies the expected result (shows Versions/Compare in the demo).
    with unit_of_work(factory) as uow:
        first = td_queries.case_by_key(uow.session, ctx, "SPARK-TC-1")
        if first is not None:
            testdesign.update_content(
                uow,
                ctx,
                first.id,
                content=td_rules.Content(
                    format=CaseFormat.steps,
                    title="Login with valid credentials",
                    preconditions="User `qa.user@acme.test` exists and is active.",
                    steps=(
                        td_rules.StepContent("Open the sign-in page", "The sign-in form is displayed", None),
                        td_rules.StepContent(
                            "Enter a valid email and password and select **Sign in**",
                            "The Energy Dashboard loads within 3 s and shows the user's name",
                            None,
                        ),
                    ),
                ),
                change_note="Clarified the dashboard check",
                row_version=first.row_version,
            )
    return f"{len(folder_ids)} folders and {n_cases} cases in SPARK"


# -- plans and cycles (M3) ------------------------------------------------------------------------


@step("SPARK plan and cycle", profiles=("dev",))
def seed_plans_and_cycles(profile: str) -> str:
    """A regression plan over the SPARK cases and an active cycle created from it (US-070…087).

    Gives the Plans and Cycles screens real content: a plan with a case list and a cycle whose runs
    are assigned to the QA engineer, so the whole M3 flow is visible in `make seed`.
    """
    from tcms.core.enums import PlanType
    from tcms.core.pagination import PageParams
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.execution import queries as exec_queries
    from tcms.execution import service as execution
    from tcms.planning import queries as planning_queries
    from tcms.planning import service as planning
    from tcms.testdesign import queries as td_queries

    page = PageParams(page=1, page_size=200)

    del profile
    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        org = workspace_queries.organization_by_slug(s, ORG_SLUG)
        if org is None:
            return "no organization — run the workspace step first"
        spark = next(
            (p for p in workspace_queries.projects(s, org.id, ids=None, status=None) if p.key == "SPARK"),
            None,
        )
        if spark is None:
            return "no SPARK project"
        members = {m.user.email: m.user.id for m in identity_queries.project_members(s, org.id, spark.id)}
    manager = members.get("ayesha@acme.test")
    engineer = members.get("sana@acme.test")
    if manager is None or engineer is None:
        return "SPARK team is missing — run the workspace step first"

    ctx = AccessContext.for_principal(
        Principal(manager, org.id, False, display_name="Ayesha Raza"),
        META,
        project_id=spark.id,
        permissions=PROJECT_PERMISSIONS,
    )
    ctx.project_status = "active"

    with factory() as s:
        existing = planning_queries.list_plans(s, ctx, {}, page)
        if existing[1] > 0:
            return "SPARK already has plans — nothing to do"
        root_folders = [
            f for f in td_queries.folder_tree(s, ctx, include_archived=False) if f.parent_id is None
        ]
        env = next(
            (e for e in workspace_queries.environments(s, org.id, spark.id, include_archived=False)),
            None,
        )
    if env is None:
        return "SPARK has no environment"

    # A plan that selects every case under the top-level folders.
    with unit_of_work(factory) as uow:
        plan = planning.create_plan(
            uow,
            ctx,
            planning.PlanData(
                name="SPARK v2.5 regression",
                type=PlanType.regression,
                objectives="Full regression ahead of the v2.5 release.",
                environment_ids=[env.id],
                exit_rules=[
                    {"type": "min_execution_progress", "threshold": 1.0},
                    {"type": "max_failed", "threshold": 0},
                ],
                risks=[
                    {"description": "Payment gateway can be flaky", "impact": "medium", "mitigation": "Retry"}
                ],
            ),
        )
        uow.session.flush()
        result = planning.add_cases(
            uow,
            ctx,
            plan.id,
            case_ids=None,
            folder_ids=[f.id for f in root_folders],
            include_subfolders=True,
            tags=None,
            saved_view_id=None,
        )
        plan_id = plan.id
        added = result.added

    # A cycle created from the plan, started, with runs assigned to the QA engineer.
    with unit_of_work(factory) as uow:
        created = execution.create_cycle(
            uow,
            ctx,
            execution.CycleData(
                name="Regression Cycle 1",
                environment_id=env.id,
                plan_id=plan_id,
                selection=execution.Selection(from_plan=True),
            ),
        )
        uow.session.flush()
        cycle_id = created.cycle.id
        run_ids = [r.run.id for r in exec_queries.list_runs(uow.session, ctx, cycle_id, {}, page)[0]]
        if run_ids:
            execution.assign_runs(uow, ctx, cycle_id, run_ids=run_ids, filter_=None, assignee_id=engineer)
        execution.start_cycle(uow, ctx, cycle_id)

    return f"SPARK plan with {added} cases and a started cycle of {len(run_ids)} runs"


# -- execution (M4) -------------------------------------------------------------------------------

# Outcomes Sana records on the first runs of SPARK-CY-1, in position order: (step status for every step,
# explicit outcome, reason). The last one stays a draft (in progress).
EXECUTIONS: tuple[tuple[str, str | None, str | None], ...] = (
    ("passed", None, None),
    ("passed", None, None),
    ("failed", None, None),
    ("passed", None, None),
    ("blocked", None, "Payment sandbox was down"),
    ("passed", None, None),
    ("skipped", "not_applicable", "Feature disabled for this tenant"),
    ("draft", None, None),
)


@step("SPARK executed results", profiles=("dev",))
def seed_results(profile: str) -> str:
    """Real attempts on SPARK-CY-1 through the runner services (US-090…092), so cycles, plans and My Work
    show progress."""
    from tcms.core.pagination import PageParams
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.execution import queries as exec_queries
    from tcms.execution import service as execution

    del profile
    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        org = workspace_queries.organization_by_slug(s, ORG_SLUG)
        spark = (
            next(
                (p for p in workspace_queries.projects(s, org.id, ids=None, status=None) if p.key == "SPARK"),
                None,
            )
            if org
            else None
        )
        if org is None or spark is None:
            return "no SPARK project"
        members = {m.user.email: m.user.id for m in identity_queries.project_members(s, org.id, spark.id)}
    engineer = members.get("sana@acme.test")
    if engineer is None:
        return "Sana is not a SPARK member"
    ctx = AccessContext.for_principal(
        Principal(engineer, org.id, False, display_name="Sana Malik"),
        META,
        project_id=spark.id,
        permissions=PROJECT_PERMISSIONS,
    )
    with factory() as s:
        cycle = exec_queries.cycle_by_key(s, ctx, "SPARK-CY-1")
        if cycle is None:
            return "no SPARK-CY-1 — run the plan and cycle step first"
        rows, _ = exec_queries.list_runs(s, ctx, cycle.id, {}, PageParams(page=1, page_size=200))
        if any(r.run.status.value != "not_run" for r in rows):
            return "SPARK-CY-1 already has results — nothing to do"
        run_ids = [r.run.id for r in rows[: len(EXECUTIONS)]]
    recorded = 0
    for run_id, (status, outcome, reason) in zip(run_ids, EXECUTIONS, strict=False):
        with unit_of_work(factory) as uow:
            res = execution.start_attempt(uow, ctx, run_id).result
            uow.session.flush()
            steps = exec_queries.result_detail(uow.session, ctx, res.id).steps
            for i, st in enumerate(steps):
                if status == "draft":
                    if i == 0:
                        execution.record_step(uow, ctx, res.id, st.step_id, fields={"status": "passed"})
                    continue
                fields: dict[str, str] = {"status": status if i == len(steps) - 1 else "passed"}
                if status == "skipped":
                    fields["status"] = "skipped"
                if fields["status"] == "failed":
                    fields["actual_result"] = (
                        "The dashboard took 9 s to load; a spinner was shown the whole time."
                    )
                execution.record_step(uow, ctx, res.id, st.step_id, fields=fields)
            if status != "draft":
                execution.finalize_attempt(
                    uow, ctx, res.id, outcome=outcome, reason=reason, duration_seconds=None
                )
                recorded += 1
    return f"{recorded} results and 1 draft on SPARK-CY-1"


@step("SPARK bug links", profiles=("dev",))
def seed_bug_links(profile: str) -> str:
    """ADR-023: SPARK tracks bugs in Jira; SPK-431 is linked to the failed seeded result (and its step) and
    SPK-440 to a case directly, so the runner, cycle, case and Bugs pages show links."""
    from tcms.bugs import queries as bug_queries
    from tcms.bugs import service as bugs
    from tcms.core.pagination import PageParams
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.execution import queries as exec_queries

    del profile
    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        org = workspace_queries.organization_by_slug(s, ORG_SLUG)
        spark = (
            next(
                (p for p in workspace_queries.projects(s, org.id, ids=None, status=None) if p.key == "SPARK"),
                None,
            )
            if org
            else None
        )
        if org is None or spark is None:
            return "no SPARK project"
        members = {m.user.email: m.user.id for m in identity_queries.project_members(s, org.id, spark.id)}
        spark_version = spark.row_version
    engineer, manager = members.get("sana@acme.test"), members.get("ayesha@acme.test")
    if engineer is None or manager is None:
        return "Sana or Ayesha is not a SPARK member"

    def ctx_for(user_id: UUID, name: str) -> AccessContext:
        return AccessContext.for_principal(
            Principal(user_id, org.id, False, display_name=name),
            META,
            project_id=spark.id,
            permissions=PROJECT_PERMISSIONS,
        )

    sana, ayesha = ctx_for(engineer, "Sana Malik"), ctx_for(manager, "Ayesha Raza")
    with factory() as s:
        if bug_queries.bug_list(s, sana, q=None, cycle_id=None, failing=False):
            return "SPARK already has bug links — nothing to do"
        cycle = exec_queries.cycle_by_key(s, sana, "SPARK-CY-1")
        if cycle is None:
            return "no SPARK-CY-1 — run the plan and cycle step first"
        rows, _ = exec_queries.list_runs(s, sana, cycle.id, {}, PageParams(page=1, page_size=200))
        failed = next((r.run for r in rows if r.run.status.value == "failed"), None)
        if failed is None or failed.latest_result_id is None:
            return "no failed run on SPARK-CY-1 — run the executed results step first"
        result = exec_queries.result_detail(s, sana, failed.latest_result_id)
        failed_step = next((st.step_id for st in result.steps if st.status == "failed"), None)
        other_case = next(
            (r.run.test_case_id for r in rows if r.run.test_case_id != failed.test_case_id), None
        )
    with unit_of_work(factory) as uow:
        workspace.update_project(
            uow,
            ayesha,
            row_version=spark_version,
            name=None,
            description=None,
            description_set=False,
            settings={
                "bug_tracker_name": "Jira",
                "bug_url_template": "https://acme.atlassian.net/browse/{ref}",
            },
            policy=workspace_queries.org_policy(uow.session, org.id),
        )
    with unit_of_work(factory) as uow:
        bugs.link_to_result(
            uow,
            sana,
            result.id,
            reference="SPK-431",
            url=None,
            title="Dashboard takes 9 s to load after sign-in",
            step_id=failed_step,
        )
        if other_case is not None:
            bugs.link_to_case(
                uow, sana, other_case, reference="SPK-440", url=None, title="Copy typo on login page"
            )
    return "Jira tracker settings, SPK-431 on the failed SPARK-CY-1 result, SPK-440 on a case"


@step("SPARK requirement references", profiles=("dev",))
def seed_requirement_refs(profile: str) -> str:
    """ADR-024: SPARK's stories live in Jira; Assay links SPK-101…104 to cases and lists SPK-105 on
    SPARK-PL-1 with no case, so the Traceability page shows covered, failing and not covered requirements."""
    from tcms.core.pagination import PageParams
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.planning import queries as plan_queries
    from tcms.planning import service as planning
    from tcms.requirements import queries as req_queries
    from tcms.requirements import service as requirements
    from tcms.testdesign import queries as td_queries

    del profile
    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        org = workspace_queries.organization_by_slug(s, ORG_SLUG)
        spark = (
            next(
                (p for p in workspace_queries.projects(s, org.id, ids=None, status=None) if p.key == "SPARK"),
                None,
            )
            if org
            else None
        )
        if org is None or spark is None:
            return "no SPARK project"
        members = {m.user.email: m.user.id for m in identity_queries.project_members(s, org.id, spark.id)}
    manager = members.get("ayesha@acme.test")
    if manager is None:
        return "Ayesha is not a SPARK member"
    ctx = AccessContext.for_principal(
        Principal(manager, org.id, False, display_name="Ayesha Raza"),
        META,
        project_id=spark.id,
        permissions=PROJECT_PERMISSIONS,
    )
    with factory() as s:
        if req_queries.list_refs(s, ctx, q=None, linked=None, ref_ids=None, include_archived=True):
            return "SPARK already has requirement references — nothing to do"
        cases, _ = td_queries.list_cases(s, ctx, {"sort": "key"}, PageParams(page=1, page_size=12))
        plan = plan_queries.plan_by_key(s, ctx, "SPARK-PL-1")
    if len(cases) < 4:
        return "SPARK has too few cases — run the repository step first"
    titles = {
        "SPK-101": "Sign in with email and password",
        "SPK-102": "Reset a forgotten password",
        "SPK-103": "Energy dashboard shows today's usage",
        "SPK-104": "Meter readings import nightly",
        "SPK-105": "Export usage to CSV",
    }
    plan_cases = {"SPK-101": cases[0:2], "SPK-102": cases[2:3], "SPK-103": cases[3:5], "SPK-104": cases[5:7]}
    with unit_of_work(factory) as uow:
        # No requirement address: links fall back to the bug tracker address set by the bug links step.
        for ref, title in titles.items():
            row = requirements.ensure_refs(uow, ctx, [ref], title=title).refs[0]
            linked = [c.id for c in plan_cases.get(ref, [])]
            if linked:
                requirements.link(uow, ctx, [row], linked)
        if plan is not None:
            planning.link_requirements(uow, ctx, plan.id, references=" ".join(titles))
    return "SPK-101…105 linked to SPARK cases; all listed on SPARK-PL-1 (SPK-105 has no case)"
