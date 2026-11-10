"""Auth and current-user endpoints (docs/06 §4.1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from tcms.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Auth,
    PublicAuth,
    ReadUow,
    Uow,
    app_state,
    policy_loader,
    request_meta,
    user_context,
)
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.core.uow import UnitOfWork, unit_of_work
from tcms.identity import queries as identity_queries
from tcms.identity import schemas as s
from tcms.identity import service as identity
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["auth"])


def _set_session_cookies(request: Request, response: Response, issued: identity.IssuedSession) -> None:
    secure = app_state(request).settings.session_cookie_secure
    max_age = max(0, int((issued.expires_at - clock.now()).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE, issued.token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )
    response.set_cookie(
        CSRF_COOKIE, issued.csrf, max_age=max_age, httponly=False, secure=secure, samesite="lax", path="/"
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/auth/login", response_model=s.LoginResponse, dependencies=PublicAuth)
def login(body: s.LoginRequest, request: Request, response: Response) -> s.LoginResponse:
    """AC-AUTH-01/02/03. Unknown email and wrong password answer identically."""
    state = app_state(request)
    with unit_of_work(state.session_factory) as uow:
        outcome = identity.login(
            uow,
            email=body.email,
            password=body.password,
            meta=request_meta(request),
            policy_for=policy_loader(uow.session),
        )
    result = outcome.unwrap()  # after commit: failures are recorded even though we answer 401/423
    _set_session_cookies(request, response, result.session)
    return s.LoginResponse(
        mfa_required=result.mfa_required, mfa_enrollment_required=result.mfa_enrollment_required
    )


@router.post("/auth/mfa/verify", status_code=status.HTTP_204_NO_CONTENT, dependencies=PublicAuth)
def mfa_verify(body: s.MfaVerifyRequest, request: Request, response: Response) -> None:
    state = app_state(request)
    with unit_of_work(state.session_factory) as uow:
        outcome = identity.verify_mfa(
            uow,
            state.settings,
            session_token=request.cookies.get(SESSION_COOKIE),
            code=body.code,
            recovery_code=body.recovery_code,
            meta=request_meta(request),
            policy_for=policy_loader(uow.session),
        )
    _set_session_cookies(request, response, outcome.unwrap())


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: identity.Authenticated = Auth,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> None:
    if auth.session_id is not None:
        identity.logout(uow, ctx, auth.session_id)
    _clear_session_cookies(response)


@router.get("/auth/me", response_model=s.MeResponse)
def me(auth: identity.Authenticated = Auth, uow: UnitOfWork = ReadUow) -> s.MeResponse:
    data = identity_queries.me(uow.session, auth)
    org = workspace_queries.organization(uow.session, auth.organization_id)
    assert org is not None
    projects = {
        p.id: p
        for p in workspace_queries.projects(
            uow.session, auth.organization_id, ids={m.project_id for m in data.memberships}, status=None
        )
    }
    return s.MeResponse(
        user=s.UserRef(**vars(data.user)),
        time_zone=data.time_zone,
        organization=s.OrganizationBrief(id=org.id, name=org.name, slug=org.slug),
        is_org_admin=data.is_org_admin,
        mfa=s.MfaStatus(enrolled=data.mfa_enrolled, required=data.mfa_required),
        memberships=[
            s.MembershipRead(
                project=s.ProjectBrief(id=p.id, key=p.key, name=p.name, status=p.status),
                role=s.RoleBrief(code=m.role_code, name=m.role_name),
                permissions=sorted(m.permissions),
            )
            for m in data.memberships
            if (p := projects.get(m.project_id)) is not None
        ],
        org_permissions=sorted(data.org_permissions),
    )


@router.patch("/auth/me", response_model=s.UserRef)
def update_me(
    body: s.ProfilePatch, ctx: AccessContext = Depends(user_context), uow: UnitOfWork = Uow
) -> s.UserRef:
    user = identity.update_profile(uow, ctx, display_name=body.display_name, time_zone=body.time_zone)
    return s.UserRef(id=user.id, display_name=user.display_name, email=user.email, is_active=user.is_active)


@router.post("/auth/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: s.PasswordChangeRequest,
    auth: identity.Authenticated = Auth,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> None:
    identity.change_password(
        uow,
        ctx,
        current_password=body.current_password,
        new_password=body.new_password,
        session_id=auth.session_id,
    )


@router.post("/auth/password/forgot", status_code=status.HTTP_202_ACCEPTED, dependencies=PublicAuth)
def forgot_password(body: s.ForgotPasswordRequest, request: Request, uow: UnitOfWork = Uow) -> None:
    """Always 202 (no account enumeration)."""
    identity.forgot_password(uow, app_state(request).settings, email=body.email, meta=request_meta(request))


@router.post("/auth/password/reset", status_code=status.HTTP_204_NO_CONTENT, dependencies=PublicAuth)
def reset_password(body: s.ResetPasswordRequest, request: Request, uow: UnitOfWork = Uow) -> None:
    identity.reset_password(
        uow,
        token=body.token,
        new_password=body.new_password,
        revoke_api_tokens=body.revoke_api_tokens,
        meta=request_meta(request),
    )


@router.post("/auth/mfa/setup", response_model=s.MfaSetupResponse)
def mfa_setup(
    request: Request, ctx: AccessContext = Depends(user_context), uow: UnitOfWork = Uow
) -> s.MfaSetupResponse:
    out = identity.mfa_setup(uow, app_state(request).settings, ctx)
    return s.MfaSetupResponse(secret=out.secret, otpauth_uri=out.otpauth_uri, setup_token=out.setup_token)


@router.post("/auth/mfa/enable", response_model=s.RecoveryCodesResponse)
def mfa_enable(
    body: s.MfaEnableRequest,
    request: Request,
    auth: identity.Authenticated = Auth,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> s.RecoveryCodesResponse:
    codes = identity.mfa_enable(
        uow,
        app_state(request).settings,
        ctx,
        setup_token=body.setup_token,
        code=body.code,
        session_id=auth.session_id,
    )
    return s.RecoveryCodesResponse(recovery_codes=codes)


@router.post("/auth/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(
    body: s.MfaDisableRequest,
    request: Request,
    auth: identity.Authenticated = Auth,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> None:
    identity.mfa_disable(
        uow, app_state(request).settings, ctx, password=body.password, code=body.code, policy=auth.policy
    )


@router.post("/auth/mfa/recovery-codes", response_model=s.RecoveryCodesResponse)
def regenerate_recovery_codes(
    body: s.PasswordConfirmRequest,
    request: Request,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> s.RecoveryCodesResponse:
    codes = identity.regenerate_recovery_codes(uow, app_state(request).settings, ctx, password=body.password)
    return s.RecoveryCodesResponse(recovery_codes=codes)


@router.get("/auth/invitations/{token}", response_model=s.InvitationInfo, dependencies=PublicAuth)
def invitation_info(token: str, uow: UnitOfWork = ReadUow) -> s.InvitationInfo:
    inv = identity.invitation_for_token(uow, token)
    org = workspace_queries.organization(uow.session, inv.organization_id)
    if org is None:
        raise NotFound()
    inviter = identity_queries.user_refs(uow.session, {inv.invited_by} if inv.invited_by else set()).get(
        inv.invited_by  # type: ignore[arg-type]
    )
    project = (
        workspace_queries.project_ref(uow.session, inv.organization_id, inv.project_id)
        if inv.project_id
        else None
    )
    return s.InvitationInfo(
        email=inv.email,
        organization=s.OrganizationBrief(id=org.id, name=org.name, slug=org.slug),
        inviter=inviter.display_name if inviter else None,
        project=s.ProjectBrief(id=project.id, key=project.key, name=project.name, status=project.status)
        if project
        else None,
        expires_at=inv.expires_at,
    )


@router.post("/auth/invitations/{token}/accept", response_model=s.LoginResponse, dependencies=PublicAuth)
def accept_invitation(
    token: str,
    body: s.AcceptInvitationRequest,
    request: Request,
    response: Response,
    uow: UnitOfWork = Uow,
) -> s.LoginResponse:
    issued = identity.accept_invitation(
        uow,
        token=token,
        display_name=body.display_name,
        password=body.password,
        time_zone=body.time_zone,
        meta=request_meta(request),
        policy_for=policy_loader(uow.session),
    )
    _set_session_cookies(request, response, issued.session)
    policy = workspace_queries.org_policy(uow.session, issued.organization_id)
    required = issued.is_org_admin or policy.mfa_required_for_all
    return s.LoginResponse(mfa_required=False, mfa_enrollment_required=required)


# -- /me ------------------------------------------------------------------------------------------


@router.get("/me/sessions", response_model=list[s.SessionRead])
def my_sessions(auth: identity.Authenticated = Auth, uow: UnitOfWork = ReadUow) -> list[s.SessionRead]:
    return [
        s.SessionRead(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            ip=str(row.ip) if row.ip else None,
            user_agent=row.user_agent,
            current=row.id == auth.session_id,
        )
        for row in identity_queries.sessions_of(uow.session, auth.user_id)
    ]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_my_session(
    session_id: UUID, ctx: AccessContext = Depends(user_context), uow: UnitOfWork = Uow
) -> None:
    identity.revoke_own_session(uow, ctx, session_id)


def _token_read(t: object) -> dict[str, object]:
    return {
        k: getattr(t, k)
        for k in (
            "id",
            "name",
            "token_prefix",
            "scope",
            "project_id",
            "expires_at",
            "last_used_at",
            "revoked_at",
            "created_at",
        )
    }


@router.get("/me/api-tokens", response_model=list[s.ApiTokenRead])
def my_tokens(auth: identity.Authenticated = Auth, uow: UnitOfWork = ReadUow) -> list[s.ApiTokenRead]:
    return [
        s.ApiTokenRead.model_validate(_token_read(t))
        for t in identity_queries.api_tokens_of(uow.session, auth.user_id)
    ]


@router.post("/me/api-tokens", response_model=s.ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    body: s.ApiTokenCreate,
    auth: identity.Authenticated = Auth,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Uow,
) -> s.ApiTokenCreated:
    if (
        body.project_id is not None
        and identity_queries.project_permissions(uow.session, auth, body.project_id) is None
    ):
        raise NotFound("Project not found")
    created = identity.create_api_token(
        uow,
        ctx,
        name=body.name,
        scope=body.scope,
        expires_in_days=body.expires_in_days,
        project_id=body.project_id,
    )
    return s.ApiTokenCreated.model_validate({**_token_read(created.token), "token": created.secret})


@router.delete("/me/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: UUID, ctx: AccessContext = Depends(user_context), uow: UnitOfWork = Uow) -> None:
    identity.revoke_api_token(uow, ctx, token_id)
