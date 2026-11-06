"""FastAPI dependencies shared by routers (docs/04 §3.3, docs/03 §9).

Authentication runs in its own short write transaction (session touch, admin-access audit), before the
route's own Unit of Work (docs/ops/00-review.md G2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from tcms.bugs import queries as bugs_queries
from tcms.core.config import Settings
from tcms.core.context import AccessContext, RequestMeta
from tcms.core.crypto import constant_time_equals
from tcms.core.errors import NotFound, RowVersionRequired, Unauthenticated
from tcms.core.uow import AuditTarget, UnitOfWork, unit_of_work
from tcms.execution import queries as execution_queries
from tcms.identity import queries as identity_queries
from tcms.identity import rules as identity_rules
from tcms.identity import service as identity
from tcms.identity.errors import CsrfFailed, MfaEnrollmentRequired, MfaRequired, TokenScopeInsufficient
from tcms.planning import queries as planning_queries
from tcms.platform import attachments, comments
from tcms.platform.audit import queries as audit_queries
from tcms.testdesign import queries as testdesign_queries
from tcms.workspace import queries as workspace_queries
from tcms.workspace.errors import ProjectArchived

SESSION_COOKIE = "tcms_session"
CSRF_COOKIE = "tcms_csrf"
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class AppState:
    settings: Settings
    session_factory: sessionmaker[Session]
    store: attachments.Storage | None = None


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.tcms
    return state


def settings_dep(request: Request) -> Settings:
    return app_state(request).settings


def get_uow(request: Request) -> Iterator[UnitOfWork]:
    """One read-write transaction per request (POST/PUT/PATCH/DELETE)."""
    with unit_of_work(app_state(request).session_factory) as uow:
        yield uow


def get_read_uow(request: Request) -> Iterator[UnitOfWork]:
    """Read-only transaction for GET routes."""
    with unit_of_work(app_state(request).session_factory, read_only=True) as uow:
        yield uow


def _client_ip(request: Request) -> str | None:
    """Only real IP addresses are stored (sessions.ip / login_attempts.ip are `inet`)."""
    import ipaddress

    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        request_id=getattr(request.state, "request_id", "req_unknown"),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def policy_loader(session: Session) -> Callable[[UUID], Any]:
    return lambda org_id: workspace_queries.org_policy(session, org_id)


# -- public endpoints: origin check + auth rate limit ---------------------------------------------


def same_origin(request: Request) -> None:
    """CSRF defence for unauthenticated POSTs (login, reset, accept): reject foreign Origins (G15)."""
    if request.method not in UNSAFE:
        return
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != app_state(request).settings.origin:
        raise CsrfFailed("Cross-origin request rejected")


def auth_rate_limit(request: Request) -> None:
    state = app_state(request)
    with unit_of_work(state.session_factory) as uow:
        identity.check_auth_rate_limit(uow, request_meta(request).ip, state.settings.rate_limit_auth_per_min)


PublicAuth = [Depends(same_origin), Depends(auth_rate_limit)]


# -- authentication -------------------------------------------------------------------------------


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


def authenticated(request: Request) -> identity.Authenticated:
    cached: identity.Authenticated | None = getattr(request.state, "auth", None)
    if cached is not None:
        return cached
    state = app_state(request)
    header = request.headers.get("authorization", "")
    cookie_token = request.cookies.get(SESSION_COOKIE)
    with unit_of_work(state.session_factory) as uow:
        loader = policy_loader(uow.session)
        if header.lower().startswith("bearer "):
            outcome = identity.authenticate_api_token(uow, header[7:].strip(), policy_for=loader)
        elif cookie_token:
            outcome = identity.authenticate_session(uow, cookie_token, policy_for=loader)
        else:
            raise Unauthenticated()
    auth = outcome.unwrap()

    if auth.session_id is not None and request.method in UNSAFE:
        header_token = request.headers.get("x-csrf-token", "")
        cookie_csrf = request.cookies.get(CSRF_COOKIE, "")
        if not header_token or not cookie_csrf or not constant_time_equals(header_token, cookie_csrf):
            raise CsrfFailed()
    if auth.token_scope == "read" and request.method in UNSAFE:  # noqa: S105 — scope name, not a secret
        raise TokenScopeInsufficient()

    gate = auth.mfa_gate
    if gate is identity_rules.MfaGate.verify:
        raise MfaRequired("Complete two-step verification first")
    if (
        gate is identity_rules.MfaGate.enroll
        and (request.method, _route_path(request)) not in identity_rules.ENROLLMENT_ALLOWED
    ):
        raise MfaEnrollmentRequired()
    request.state.auth = auth
    return auth


Auth = Depends(authenticated)


def org_context(request: Request, auth: identity.Authenticated = Auth) -> AccessContext:
    state = app_state(request)
    with state.session_factory() as s:
        perms = identity_queries.org_permissions(s, auth)
    return AccessContext.for_principal(auth.principal, request_meta(request), permissions=perms)


def user_context(request: Request, auth: identity.Authenticated = Auth) -> AccessContext:
    """Authenticated user without org/project permissions (own profile, tokens, sessions)."""
    return AccessContext.for_principal(auth.principal, request_meta(request))


def _project_context(
    request: Request, auth: identity.Authenticated, project_id: UUID, *, allow_archived: bool
) -> AccessContext:
    state = app_state(request)
    with state.session_factory() as s:
        ref = workspace_queries.project_ref(s, auth.organization_id, project_id)
        perms = identity_queries.project_permissions(s, auth, project_id) if ref else None
        admin_outsider = bool(
            ref and auth.is_org_admin and not identity_queries.is_project_member(s, auth, project_id)
        )
    if ref is None or perms is None:
        raise NotFound()
    ctx = AccessContext.for_principal(
        auth.principal, request_meta(request), project_id=project_id, permissions=perms
    )
    ctx.project_status = ref.status.value
    if admin_outsider and auth.session_id is not None:
        _record_admin_access(state, ctx, auth.session_id, ref.key)
    if request.method in UNSAFE and ref.status.value == "archived" and not allow_archived:
        raise ProjectArchived()
    return ctx


def _record_admin_access(state: AppState, ctx: AccessContext, session_id: UUID, key: str) -> None:
    """Q1: an Org Admin's access to a project they are not a member of, once per session."""
    with unit_of_work(state.session_factory) as uow:
        if not audit_queries.admin_access_recorded(
            uow.session, ctx.principal.organization_id, ctx.pid, session_id
        ):
            uow.audit(
                ctx,
                "project.admin_accessed",
                AuditTarget("project", ctx.project_id, key),
                extra={"session_id": str(session_id)},
                summary=f"{ctx.principal.display_name} (Org Admin) opened project {key}",
            )


def project_context(request: Request, project_id: UUID, auth: identity.Authenticated = Auth) -> AccessContext:
    return _project_context(request, auth, project_id, allow_archived=False)


def project_context_allow_archived(
    request: Request, project_id: UUID, auth: identity.Authenticated = Auth
) -> AccessContext:
    return _project_context(request, auth, project_id, allow_archived=True)


# entity_type -> function(session, entity_id) -> (organization_id, project_id) | None
ENTITY_PROJECT: dict[str, Callable[[Session, UUID], tuple[UUID, UUID] | None]] = {
    "environment": lambda s, i: workspace_queries.owning_project(s, "environment", i),
    "release": lambda s, i: workspace_queries.owning_project(s, "release", i),
    "test_case": testdesign_queries.owning_project_of_case,
    "folder": testdesign_queries.owning_project_of_folder,
    "tag": testdesign_queries.owning_project_of_tag,
    "test_case_version": testdesign_queries.owning_project_of_version,
    "test_case_step": testdesign_queries.owning_project_of_step,
    "test_plan": planning_queries.owning_project_of_plan,
    "test_cycle": execution_queries.owning_project_of_cycle,
    "test_run": execution_queries.owning_project_of_run,
    "test_result": execution_queries.owning_project_of_result,
    "test_step_result": execution_queries.owning_project_of_step_result,
    "bug_link": bugs_queries.owner_of_link,
    "comment": comments.owner_of,
    "attachment": attachments.owner_of,
}


def project_context_for(
    request: Request, auth: identity.Authenticated, entity_type: str, entity_id: UUID
) -> AccessContext:
    """Same as `project_context_from`, for entities named in the body or query (comments, attachments)."""
    resolver = ENTITY_PROJECT.get(entity_type)
    if resolver is None:
        raise NotFound()
    with app_state(request).session_factory() as s:
        owner = resolver(s, entity_id)
    if owner is None or owner[0] != auth.organization_id:
        raise NotFound()
    return _project_context(request, auth, owner[1], allow_archived=False)


def project_context_from(entity_type: str, param: str) -> Callable[..., AccessContext]:
    """Resolve the project of an entity addressed by ID, then build its AccessContext (04 §3.3)."""
    resolver = ENTITY_PROJECT[entity_type]

    def dependency(request: Request, auth: identity.Authenticated = Auth) -> AccessContext:
        raw = request.path_params.get(param)
        try:
            entity_id = UUID(str(raw))
        except ValueError as exc:
            raise NotFound() from exc
        with app_state(request).session_factory() as s:
            owner = resolver(s, entity_id)
        if owner is None or owner[0] != auth.organization_id:
            raise NotFound()
        return _project_context(request, auth, owner[1], allow_archived=False)

    return dependency


def resolve_row_version(body_value: int | None, if_match: str | None) -> int:
    """BR-25: `row_version` in the body or `If-Match: "<n>"`; missing → 428 (docs/06 §2.7)."""
    if body_value is not None:
        return body_value
    if if_match:
        try:
            return int(if_match.strip().strip("W/").strip('"'))
        except ValueError:
            pass
    raise RowVersionRequired()
