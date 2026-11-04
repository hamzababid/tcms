-- 01_baseline.sql — TCMS MVP baseline schema (PostgreSQL 16).
-- Authoritative executable form of docs/05-Database-Design.md. The first Alembic migration
-- must produce exactly this schema (it may execute this file verbatim).
-- Run as tcms_owner in database tcms. Requires 00_roles.sql to have been run.

BEGIN;

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------------------------------------------------------------------------
-- Enum types (docs/05 §2)
-- ---------------------------------------------------------------------------
CREATE TYPE project_status        AS ENUM ('active','archived');
CREATE TYPE release_status        AS ENUM ('planned','active','released','archived');
CREATE TYPE release_decision_kind AS ENUM ('go','go_with_risks','no_go');
CREATE TYPE priority_level        AS ENUM ('critical','high','medium','low');
CREATE TYPE case_status           AS ENUM ('draft','in_review','approved','deprecated','archived');
CREATE TYPE case_format           AS ENUM ('steps','text');
CREATE TYPE case_type             AS ENUM ('functional','integration','end_to_end','api','ui','data_validation',
                                           'performance','security','compatibility','usability');
CREATE TYPE design_technique      AS ENUM ('positive','negative','boundary_value','equivalence_partitioning','error_guessing');
CREATE TYPE automation_status     AS ENUM ('manual','automated','to_be_automated','not_automatable');
CREATE TYPE approval_mode         AS ENUM ('auto','manual');
CREATE TYPE case_link_type        AS ENUM ('related','duplicated_from');
CREATE TYPE plan_type             AS ENUM ('functional','integration','regression','release_validation','uat','smoke',
                                           'performance','security');
CREATE TYPE plan_status           AS ENUM ('draft','active','completed','archived');
CREATE TYPE cycle_status          AS ENUM ('planned','active','closed');
CREATE TYPE run_status            AS ENUM ('not_run','in_progress','passed','failed','blocked','skipped','not_applicable');
CREATE TYPE result_state          AS ENUM ('draft','final');
CREATE TYPE result_status         AS ENUM ('passed','failed','blocked','skipped','not_applicable');
CREATE TYPE step_status           AS ENUM ('not_run','passed','failed','blocked','skipped');
CREATE TYPE result_source         AS ENUM ('manual','automation');
CREATE TYPE defect_status         AS ENUM ('open','triaged','assigned','in_progress','fixed','ready_for_retest','verified',
                                           'closed','reopened','rejected','duplicate','cannot_reproduce','deferred');
CREATE TYPE defect_resolution     AS ENUM ('fixed','wont_fix','duplicate','cannot_reproduce','not_a_bug','deferred');
CREATE TYPE requirement_type      AS ENUM ('epic','feature','user_story','functional','non_functional','business');
CREATE TYPE requirement_status    AS ENUM ('draft','approved','implemented','obsolete');
CREATE TYPE requirement_source    AS ENUM ('internal','jira');
CREATE TYPE actor_type            AS ENUM ('user','api_token','system','integration');
CREATE TYPE job_status            AS ENUM ('queued','running','succeeded','failed','dead');
CREATE TYPE transfer_kind         AS ENUM ('import','export');
CREATE TYPE transfer_status       AS ENUM ('uploaded','validating','validated','committing','committed','generating',
                                           'ready','failed','expired');
CREATE TYPE view_visibility       AS ENUM ('private','project');
CREATE TYPE token_scope           AS ENUM ('read','read_write');

-- Sentinel used where a nullable uuid participates in a unique expression index.
CREATE FUNCTION tcms_nil_uuid() RETURNS uuid LANGUAGE sql IMMUTABLE PARALLEL SAFE
  AS $$ SELECT '00000000-0000-0000-0000-000000000000'::uuid $$;

-- ---------------------------------------------------------------------------
-- 3.1 Identity and organization
-- Actor columns (created_by, updated_by, granted_by, …) are not FK-constrained:
-- users are never deleted, and audit/history must survive any future user purge.
-- ---------------------------------------------------------------------------
CREATE TABLE organizations (
  id            uuid PRIMARY KEY,
  name          text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  slug          text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  settings      jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  created_by    uuid,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  updated_by    uuid,
  row_version   integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_organizations__slug ON organizations (slug);

CREATE TABLE users (
  id                   uuid PRIMARY KEY,
  email                citext NOT NULL CHECK (char_length(email) <= 254),
  display_name         text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 100),
  password_hash        text,
  time_zone            text NOT NULL DEFAULT 'UTC',
  is_active            boolean NOT NULL DEFAULT true,
  failed_login_count   integer NOT NULL DEFAULT 0,
  locked_until         timestamptz,
  last_login_at        timestamptz,
  password_changed_at  timestamptz,
  preferences          jsonb NOT NULL DEFAULT '{}',
  created_at           timestamptz NOT NULL DEFAULT now(),
  created_by           uuid,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  updated_by           uuid,
  row_version          integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_users__email ON users (email);

CREATE TABLE organization_members (
  organization_id uuid NOT NULL REFERENCES organizations(id),
  user_id         uuid NOT NULL REFERENCES users(id),
  is_org_admin    boolean NOT NULL DEFAULT false,
  joined_at       timestamptz NOT NULL DEFAULT now(),
  granted_by      uuid,
  PRIMARY KEY (organization_id, user_id)
);
-- MVP: one organization per user (relaxable later by dropping this index).
CREATE UNIQUE INDEX ux_organization_members__user_id ON organization_members (user_id);

CREATE TABLE roles (
  id              uuid PRIMARY KEY,
  organization_id uuid REFERENCES organizations(id),          -- NULL = system role
  code            text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]{1,49}$'),
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  description     text,
  is_system       boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  CHECK (is_system = (organization_id IS NULL))
);
CREATE UNIQUE INDEX ux_roles__organization_id_code ON roles (coalesce(organization_id, tcms_nil_uuid()), code);

CREATE TABLE role_permissions (
  role_id    uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission text NOT NULL CHECK (permission ~ '^[a-z]+(\.[a-z_]+)+$'),
  PRIMARY KEY (role_id, permission)
);

CREATE TABLE user_mfa (
  user_id          uuid PRIMARY KEY REFERENCES users(id),
  totp_secret_enc  bytea NOT NULL,
  enrolled_at      timestamptz NOT NULL DEFAULT now(),
  last_used_step   bigint
);

CREATE TABLE mfa_recovery_codes (
  id         uuid PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id),
  code_hash  text NOT NULL,
  used_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_mfa_recovery_codes__user_id ON mfa_recovery_codes (user_id);

CREATE TABLE sessions (
  id              uuid PRIMARY KEY,
  token_hash      bytea NOT NULL,
  user_id         uuid NOT NULL REFERENCES users(id),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_seen_at    timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  mfa_verified    boolean NOT NULL DEFAULT false,
  ip              inet,
  user_agent      text CHECK (char_length(user_agent) <= 500),
  revoked_at      timestamptz
);
CREATE UNIQUE INDEX ux_sessions__token_hash ON sessions (token_hash);
CREATE INDEX ix_sessions__user_id ON sessions (user_id);
CREATE INDEX ix_sessions__expires_at ON sessions (expires_at);

CREATE TABLE password_reset_tokens (
  id         uuid PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id),
  token_hash bytea NOT NULL,
  expires_at timestamptz NOT NULL,
  used_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_password_reset_tokens__token_hash ON password_reset_tokens (token_hash);

CREATE TABLE login_attempts (
  id          bigserial PRIMARY KEY,
  email       citext,
  ip          inet,
  succeeded   boolean NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_login_attempts__email_occurred ON login_attempts (email, occurred_at);
CREATE INDEX ix_login_attempts__ip_occurred ON login_attempts (ip, occurred_at);

-- ---------------------------------------------------------------------------
-- 3.2 Workspace
-- ---------------------------------------------------------------------------
CREATE TABLE projects (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id),
  key             text NOT NULL CHECK (key ~ '^[A-Z][A-Z0-9]{1,9}$'),
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  description     text CHECK (char_length(description) <= 20000),
  status          project_status NOT NULL DEFAULT 'active',
  settings        jsonb NOT NULL DEFAULT '{}',
  archived_at     timestamptz,
  archived_by     uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  UNIQUE (organization_id, id)                                 -- target for composite FKs
);
CREATE UNIQUE INDEX ux_projects__organization_id_key ON projects (organization_id, key);
CREATE UNIQUE INDEX ux_projects__organization_id_lower_name ON projects (organization_id, lower(name))
  WHERE status = 'active';

-- Tokens and invitations reference projects, so they follow projects.
CREATE TABLE api_tokens (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id),
  user_id         uuid NOT NULL REFERENCES users(id),
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  token_prefix    text NOT NULL,
  token_hash      bytea NOT NULL,
  scope           token_scope NOT NULL,
  project_id      uuid REFERENCES projects(id),
  expires_at      timestamptz NOT NULL,
  last_used_at    timestamptz,
  revoked_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at <= created_at + interval '366 days')
);
CREATE UNIQUE INDEX ux_api_tokens__token_hash ON api_tokens (token_hash);
CREATE INDEX ix_api_tokens__user_id ON api_tokens (user_id);

CREATE TABLE invitations (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id),
  email           citext NOT NULL,
  token_hash      bytea NOT NULL,
  is_org_admin    boolean NOT NULL DEFAULT false,
  project_id      uuid REFERENCES projects(id),
  role_id         uuid REFERENCES roles(id),
  invited_by      uuid,
  expires_at      timestamptz NOT NULL,
  accepted_at     timestamptz,
  revoked_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK ((project_id IS NULL) = (role_id IS NULL))
);
CREATE UNIQUE INDEX ux_invitations__token_hash ON invitations (token_hash);
CREATE INDEX ix_invitations__organization_id_email ON invitations (organization_id, email);

CREATE TABLE project_members (
  project_id      uuid NOT NULL,
  user_id         uuid NOT NULL REFERENCES users(id),
  organization_id uuid NOT NULL,
  role_id         uuid NOT NULL REFERENCES roles(id),
  granted_by      uuid,
  granted_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, user_id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE INDEX ix_project_members__user_id ON project_members (user_id);

CREATE TABLE environments (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 50),
  description     text,
  archived_at     timestamptz,
  archived_by     uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_environments__project_lower_name ON environments (project_id, lower(name));

CREATE TABLE releases (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 50),
  description     text,
  status          release_status NOT NULL DEFAULT 'planned',
  start_date      date,
  target_date     date,
  released_at     timestamptz,
  archived_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  CHECK (target_date IS NULL OR start_date IS NULL OR target_date >= start_date),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_releases__project_lower_name ON releases (project_id, lower(name));

CREATE TABLE release_decisions (                                 -- append-only
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  release_id      uuid NOT NULL REFERENCES releases(id),
  decision        release_decision_kind NOT NULL,
  comment         text NOT NULL CHECK (char_length(comment) BETWEEN 1 AND 20000),
  risks           text,
  snapshot        jsonb NOT NULL,
  decided_by      uuid NOT NULL,
  decided_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (decision <> 'go_with_risks' OR coalesce(char_length(risks), 0) > 0),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE INDEX ix_release_decisions__release_id_decided_at ON release_decisions (release_id, decided_at DESC);

CREATE TABLE key_sequences (
  project_id uuid NOT NULL REFERENCES projects(id),
  entity     text NOT NULL CHECK (entity IN ('test_case','test_plan','test_cycle','defect','requirement')),
  next_value bigint NOT NULL DEFAULT 1 CHECK (next_value >= 1),
  PRIMARY KEY (project_id, entity)
);

-- ---------------------------------------------------------------------------
-- 3.3 Test design
-- ---------------------------------------------------------------------------
CREATE TABLE folders (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  parent_id       uuid REFERENCES folders(id),
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120 AND position('/' in name) = 0),
  description     text,
  position        integer NOT NULL DEFAULT 0,
  path            text NOT NULL,                               -- "/<root-id>/…/<own-id>/"
  depth           smallint NOT NULL CHECK (depth BETWEEN 1 AND 10),
  case_count      integer NOT NULL DEFAULT 0 CHECK (case_count >= 0),
  archived_at     timestamptz,
  archived_by     uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  CHECK (parent_id IS NULL OR parent_id <> id),
  CHECK (path LIKE '%/' || id::text || '/'),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_folders__project_parent_lower_name
  ON folders (project_id, coalesce(parent_id, tcms_nil_uuid()), lower(name));
CREATE INDEX ix_folders__project_id_path ON folders (project_id, path text_pattern_ops);
CREATE INDEX ix_folders__parent_id ON folders (parent_id);

CREATE TABLE test_cases (
  id                   uuid PRIMARY KEY,
  organization_id      uuid NOT NULL,
  project_id           uuid NOT NULL,
  key_num              bigint NOT NULL CHECK (key_num >= 1),
  key                  text NOT NULL,
  folder_id            uuid NOT NULL REFERENCES folders(id),
  title                text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 255),
  format               case_format NOT NULL DEFAULT 'steps',
  type                 case_type NOT NULL DEFAULT 'functional',
  design_technique     design_technique,
  priority             priority_level NOT NULL DEFAULT 'medium',
  status               case_status NOT NULL,
  owner_id             uuid NOT NULL REFERENCES users(id),
  reviewer_id          uuid REFERENCES users(id),
  automation_status    automation_status NOT NULL DEFAULT 'manual',
  estimated_minutes    integer CHECK (estimated_minutes BETWEEN 0 AND 1440),
  latest_version_id    uuid,                                   -- FK added below (deferrable)
  approved_version_id  uuid,                                   -- FK added below (deferrable)
  latest_version_no    integer NOT NULL DEFAULT 1,
  search_vector        tsvector NOT NULL DEFAULT ''::tsvector,
  archived_at          timestamptz,
  archived_by          uuid,
  created_at           timestamptz NOT NULL DEFAULT now(),
  created_by           uuid,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  updated_by           uuid,
  row_version          integer NOT NULL DEFAULT 1,
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_test_cases__project_id_key_num ON test_cases (project_id, key_num);
CREATE UNIQUE INDEX ux_test_cases__project_id_key ON test_cases (project_id, key);
CREATE INDEX ix_test_cases__project_folder_status ON test_cases (project_id, folder_id, status);
CREATE INDEX ix_test_cases__project_status_priority ON test_cases (project_id, status, priority);
CREATE INDEX ix_test_cases__owner_id ON test_cases (owner_id);
CREATE INDEX ix_test_cases__search_vector ON test_cases USING gin (search_vector);
CREATE INDEX ix_test_cases__title_trgm ON test_cases USING gin (title gin_trgm_ops);

CREATE TABLE test_case_versions (                                -- immutable except submission/approval
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  test_case_id     uuid NOT NULL,
  version_no       integer NOT NULL CHECK (version_no >= 1),
  format           case_format NOT NULL,
  title            text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 255),
  description      text CHECK (char_length(description) <= 20000),
  preconditions    text CHECK (char_length(preconditions) <= 20000),
  test_data        text CHECK (char_length(test_data) <= 20000),
  expected_result  text CHECK (char_length(expected_result) <= 20000),
  postconditions   text CHECK (char_length(postconditions) <= 20000),
  text_body        text CHECK (char_length(text_body) <= 20000),
  change_note      text CHECK (char_length(change_note) <= 500),
  content_hash     bytea NOT NULL,
  created_by       uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  submitted_by     uuid,
  submitted_at     timestamptz,
  approved_by      uuid,
  approved_at      timestamptz,
  approval_mode    approval_mode,
  CHECK (format <> 'text' OR text_body IS NOT NULL),
  CHECK ((approval_mode IS NULL AND approved_at IS NULL)
      OR (approval_mode = 'auto' AND approved_at IS NOT NULL)
      OR (approval_mode = 'manual' AND approved_at IS NOT NULL AND approved_by IS NOT NULL)),
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ux_test_case_versions__case_version ON test_case_versions (test_case_id, version_no);

ALTER TABLE test_cases
  ADD CONSTRAINT fk_test_cases_latest_version_id FOREIGN KEY (latest_version_id)
      REFERENCES test_case_versions(id) DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT fk_test_cases_approved_version_id FOREIGN KEY (approved_version_id)
      REFERENCES test_case_versions(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE test_case_steps (                                   -- immutable
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  version_id       uuid NOT NULL REFERENCES test_case_versions(id) ON DELETE CASCADE,
  position         smallint NOT NULL CHECK (position BETWEEN 1 AND 100),
  action           text NOT NULL CHECK (char_length(action) BETWEEN 1 AND 5000),
  expected_result  text CHECK (char_length(expected_result) <= 5000),
  data             text CHECK (char_length(data) <= 2000)
);
CREATE UNIQUE INDEX ux_test_case_steps__version_position ON test_case_steps (version_id, position);

CREATE TABLE tags (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  name            text NOT NULL CHECK (name ~ '^[a-z0-9._-]{1,40}$'),
  is_system       boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_tags__project_name ON tags (project_id, name);

CREATE TABLE test_case_tags (
  test_case_id uuid NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
  tag_id       uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (test_case_id, tag_id)
);
CREATE INDEX ix_test_case_tags__tag_id ON test_case_tags (tag_id);

CREATE TABLE test_case_links (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  source_case_id   uuid NOT NULL,
  target_case_id   uuid NOT NULL,
  link_type        case_link_type NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  CHECK (source_case_id <> target_case_id),
  CHECK (link_type <> 'related' OR source_case_id < target_case_id),   -- 'related' stored once
  FOREIGN KEY (project_id, source_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, target_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ux_test_case_links__pair ON test_case_links (source_case_id, target_case_id, link_type);
CREATE INDEX ix_test_case_links__target ON test_case_links (target_case_id);

CREATE TABLE automation_keys (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  test_case_id    uuid NOT NULL,
  key             text NOT NULL CHECK (char_length(key) BETWEEN 1 AND 500),
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ux_automation_keys__project_key ON automation_keys (project_id, key);
CREATE INDEX ix_automation_keys__test_case_id ON automation_keys (test_case_id);

-- ---------------------------------------------------------------------------
-- 3.7 Requirements (before planning and defects, which reference them)
-- ---------------------------------------------------------------------------
CREATE TABLE requirements (
  id                   uuid PRIMARY KEY,
  organization_id      uuid NOT NULL,
  project_id           uuid NOT NULL,
  key_num              bigint NOT NULL,
  key                  text NOT NULL,
  external_key         text,
  title                text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 255),
  description          text CHECK (char_length(description) <= 20000),
  acceptance_criteria  text CHECK (char_length(acceptance_criteria) <= 20000),
  type                 requirement_type NOT NULL,
  priority             priority_level NOT NULL DEFAULT 'medium',
  status               requirement_status NOT NULL DEFAULT 'draft',
  owner_id             uuid REFERENCES users(id),
  target_release_id    uuid REFERENCES releases(id),
  parent_id            uuid REFERENCES requirements(id),
  source               requirement_source NOT NULL DEFAULT 'internal',
  search_vector        tsvector NOT NULL DEFAULT ''::tsvector,
  archived_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  created_by           uuid,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  updated_by           uuid,
  row_version          integer NOT NULL DEFAULT 1,
  CHECK (parent_id IS NULL OR parent_id <> id),
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_requirements__project_id_key_num ON requirements (project_id, key_num);
CREATE UNIQUE INDEX ux_requirements__project_id_key ON requirements (project_id, key);
CREATE INDEX ix_requirements__project_release ON requirements (project_id, target_release_id);
CREATE INDEX ix_requirements__parent_id ON requirements (parent_id);
CREATE INDEX ix_requirements__search_vector ON requirements USING gin (search_vector);

CREATE TABLE requirement_case_links (
  requirement_id  uuid NOT NULL,
  test_case_id    uuid NOT NULL,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  PRIMARY KEY (requirement_id, test_case_id),
  FOREIGN KEY (project_id, requirement_id) REFERENCES requirements (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_requirement_case_links__test_case_id ON requirement_case_links (test_case_id);

-- ---------------------------------------------------------------------------
-- 3.4 Planning
-- ---------------------------------------------------------------------------
CREATE TABLE test_plans (
  id                   uuid PRIMARY KEY,
  organization_id      uuid NOT NULL,
  project_id           uuid NOT NULL,
  key_num              bigint NOT NULL,
  key                  text NOT NULL,
  name                 text NOT NULL CHECK (char_length(name) BETWEEN 3 AND 150),
  type                 plan_type NOT NULL,
  status               plan_status NOT NULL DEFAULT 'draft',
  release_id           uuid REFERENCES releases(id),
  owner_id             uuid NOT NULL REFERENCES users(id),
  objectives           text,
  scope_in             text,
  scope_out            text,
  entry_criteria       text,
  exit_criteria_notes  text,
  acceptance_criteria  text,
  exit_rules           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(exit_rules) = 'array'),
  risks                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(risks) = 'array'),
  member_ids           uuid[] NOT NULL DEFAULT '{}',
  start_date           date,
  end_date             date,
  archived_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  created_by           uuid,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  updated_by           uuid,
  row_version          integer NOT NULL DEFAULT 1,
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_test_plans__project_id_key_num ON test_plans (project_id, key_num);
CREATE INDEX ix_test_plans__project_release ON test_plans (project_id, release_id);

CREATE TABLE test_plan_cases (
  plan_id         uuid NOT NULL,
  test_case_id    uuid NOT NULL,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  added_at        timestamptz NOT NULL DEFAULT now(),
  added_by        uuid,
  PRIMARY KEY (plan_id, test_case_id),
  FOREIGN KEY (project_id, plan_id) REFERENCES test_plans (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id)
);
CREATE INDEX ix_test_plan_cases__test_case_id ON test_plan_cases (test_case_id);

CREATE TABLE test_plan_requirements (
  plan_id         uuid NOT NULL,
  requirement_id  uuid NOT NULL,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  added_at        timestamptz NOT NULL DEFAULT now(),
  added_by        uuid,
  PRIMARY KEY (plan_id, requirement_id),
  FOREIGN KEY (project_id, plan_id) REFERENCES test_plans (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, requirement_id) REFERENCES requirements (project_id, id)
);
CREATE INDEX ix_test_plan_requirements__requirement_id ON test_plan_requirements (requirement_id);

CREATE TABLE test_plan_environments (
  plan_id        uuid NOT NULL REFERENCES test_plans(id) ON DELETE CASCADE,
  environment_id uuid NOT NULL REFERENCES environments(id),
  PRIMARY KEY (plan_id, environment_id)
);

-- ---------------------------------------------------------------------------
-- 3.5 Execution
-- ---------------------------------------------------------------------------
CREATE TABLE test_cycles (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  key_num         bigint NOT NULL,
  key             text NOT NULL,
  name            text NOT NULL CHECK (char_length(name) BETWEEN 3 AND 150),
  description     text,
  release_id      uuid REFERENCES releases(id),
  plan_id         uuid,
  environment_id  uuid NOT NULL REFERENCES environments(id),
  build           text CHECK (char_length(build) <= 100),
  status          cycle_status NOT NULL DEFAULT 'planned',
  start_date      date,
  due_date        date,
  owner_id        uuid NOT NULL REFERENCES users(id),
  runs_pending    boolean NOT NULL DEFAULT false,
  started_at      timestamptz,
  closed_at       timestamptz,
  closed_by       uuid,
  archived_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  CHECK (due_date IS NULL OR start_date IS NULL OR due_date >= start_date),
  CHECK ((status = 'closed') = (closed_at IS NOT NULL)),
  CHECK (archived_at IS NULL OR status = 'closed'),
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id),
  FOREIGN KEY (project_id, plan_id) REFERENCES test_plans (project_id, id)
);
CREATE UNIQUE INDEX ux_test_cycles__project_id_key_num ON test_cycles (project_id, key_num);
CREATE INDEX ix_test_cycles__project_status ON test_cycles (project_id, status);
CREATE INDEX ix_test_cycles__release_id ON test_cycles (release_id);
CREATE INDEX ix_test_cycles__plan_id ON test_cycles (plan_id);

CREATE TABLE test_runs (
  id                     uuid PRIMARY KEY,
  organization_id        uuid NOT NULL,
  project_id             uuid NOT NULL,
  cycle_id               uuid NOT NULL,
  test_case_id           uuid NOT NULL,
  test_case_version_id   uuid NOT NULL REFERENCES test_case_versions(id),
  position               integer NOT NULL,
  assignee_id            uuid REFERENCES users(id),
  status                 run_status NOT NULL DEFAULT 'not_run',
  latest_result_id       uuid,                                 -- FK added below (deferrable)
  needs_retest           boolean NOT NULL DEFAULT false,
  superseded_by_run_id   uuid,                                 -- FK added below (deferrable, BR-05)
  superseded_at          timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  created_by             uuid,
  updated_at             timestamptz NOT NULL DEFAULT now(),
  updated_by             uuid,
  row_version            integer NOT NULL DEFAULT 1,
  CHECK ((superseded_by_run_id IS NULL) = (superseded_at IS NULL)),
  CHECK (superseded_by_run_id IS NULL OR superseded_by_run_id <> id),
  UNIQUE (project_id, id),
  FOREIGN KEY (project_id, cycle_id) REFERENCES test_cycles (project_id, id),
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id)
);
CREATE UNIQUE INDEX ux_test_runs__cycle_case_active ON test_runs (cycle_id, test_case_id)
  WHERE superseded_by_run_id IS NULL;                            -- BR-12
CREATE INDEX ix_test_runs__cycle_status ON test_runs (cycle_id, status) WHERE superseded_by_run_id IS NULL;
CREATE INDEX ix_test_runs__assignee_status ON test_runs (assignee_id, status) WHERE superseded_by_run_id IS NULL;
CREATE INDEX ix_test_runs__test_case_id ON test_runs (test_case_id);
CREATE INDEX ix_test_runs__cycle_position ON test_runs (cycle_id, position);

CREATE TABLE test_results (                                      -- attempts; immutable once final
  id                  uuid PRIMARY KEY,
  organization_id     uuid NOT NULL,
  project_id          uuid NOT NULL,
  run_id              uuid NOT NULL,
  attempt_no          integer NOT NULL CHECK (attempt_no >= 1),
  state               result_state NOT NULL DEFAULT 'draft',
  status              result_status,
  source              result_source NOT NULL DEFAULT 'manual',
  executed_by         uuid REFERENCES users(id),
  started_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz,
  duration_seconds    integer CHECK (duration_seconds BETWEEN 0 AND 86400),
  build               text CHECK (char_length(build) <= 100),
  environment_id      uuid NOT NULL REFERENCES environments(id),
  comment             text CHECK (char_length(comment) <= 20000),
  reason              text CHECK (char_length(reason) <= 1000),
  skipped_steps       smallint NOT NULL DEFAULT 0 CHECK (skipped_steps >= 0),
  corrects_result_id  uuid REFERENCES test_results(id),
  automation_meta     jsonb,
  updated_at          timestamptz NOT NULL DEFAULT now(),
  updated_by          uuid,
  CHECK ((state = 'draft' AND status IS NULL AND finished_at IS NULL)
      OR (state = 'final' AND status IS NOT NULL AND finished_at IS NOT NULL)),
  CHECK (source = 'automation' OR executed_by IS NOT NULL),
  CHECK (state = 'draft' OR status NOT IN ('blocked','skipped','not_applicable')
         OR coalesce(char_length(reason), 0) > 0 OR source = 'automation'),   -- BR-10
  CHECK (corrects_result_id IS NULL OR corrects_result_id <> id),
  UNIQUE (project_id, id),
  FOREIGN KEY (project_id, run_id) REFERENCES test_runs (project_id, id)
);
CREATE UNIQUE INDEX ux_test_results__run_attempt ON test_results (run_id, attempt_no);
CREATE UNIQUE INDEX ux_test_results__run_draft ON test_results (run_id) WHERE state = 'draft';   -- BR-07
CREATE INDEX ix_test_results__project_finished ON test_results (project_id, finished_at) WHERE state = 'final';
CREATE INDEX ix_test_results__executed_by_finished ON test_results (executed_by, finished_at);

ALTER TABLE test_runs
  ADD CONSTRAINT fk_test_runs_latest_result_id FOREIGN KEY (latest_result_id)
      REFERENCES test_results(id) DEFERRABLE INITIALLY DEFERRED,
  -- Replace run marks the old run superseded before the new run exists (the partial unique index
  -- forbids two active runs), so this FK must be checked at commit.
  ADD CONSTRAINT fk_test_runs_superseded_by_run_id FOREIGN KEY (superseded_by_run_id)
      REFERENCES test_runs(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE test_step_results (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  result_id        uuid NOT NULL REFERENCES test_results(id) ON DELETE CASCADE,
  step_id          uuid NOT NULL REFERENCES test_case_steps(id),
  position         smallint NOT NULL,
  status           step_status NOT NULL DEFAULT 'not_run',
  actual_result    text CHECK (char_length(actual_result) <= 20000),
  comment          text CHECK (char_length(comment) <= 20000),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  updated_by       uuid
);
CREATE UNIQUE INDEX ux_test_step_results__result_step ON test_step_results (result_id, step_id);
CREATE INDEX ix_test_step_results__result_position ON test_step_results (result_id, position);

-- ---------------------------------------------------------------------------
-- 3.6 Defects
-- ---------------------------------------------------------------------------
CREATE TABLE defects (
  id                   uuid PRIMARY KEY,
  organization_id      uuid NOT NULL,
  project_id           uuid NOT NULL,
  key_num              bigint NOT NULL,
  key                  text NOT NULL,
  title                text NOT NULL CHECK (char_length(title) BETWEEN 5 AND 255),
  description          text CHECK (char_length(description) <= 20000),
  steps_to_reproduce   text NOT NULL CHECK (char_length(steps_to_reproduce) <= 20000),
  expected_result      text NOT NULL CHECK (char_length(expected_result) <= 20000),
  actual_result        text NOT NULL CHECK (char_length(actual_result) <= 20000),
  severity             priority_level NOT NULL DEFAULT 'medium',
  priority             priority_level NOT NULL DEFAULT 'medium',
  status               defect_status NOT NULL DEFAULT 'open',
  environment_id       uuid REFERENCES environments(id),
  build                text CHECK (char_length(build) <= 100),
  browser_device       text CHECK (char_length(browser_device) <= 200),
  folder_id            uuid REFERENCES folders(id),
  found_in_release_id  uuid REFERENCES releases(id),
  fix_version          text CHECK (char_length(fix_version) <= 100),
  reporter_id          uuid NOT NULL REFERENCES users(id),
  assignee_id          uuid REFERENCES users(id),
  resolution           defect_resolution,
  resolution_note      text CHECK (char_length(resolution_note) <= 20000),
  duplicate_of_id      uuid REFERENCES defects(id),
  external_owner       text CHECK (external_owner IN ('jira')),
  resolved_at          timestamptz,
  search_vector        tsvector NOT NULL DEFAULT ''::tsvector,
  created_at           timestamptz NOT NULL DEFAULT now(),
  created_by           uuid,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  updated_by           uuid,
  row_version          integer NOT NULL DEFAULT 1,
  CHECK (duplicate_of_id IS NULL OR duplicate_of_id <> id),
  CHECK (status <> 'duplicate' OR duplicate_of_id IS NOT NULL),
  CHECK (status <> 'assigned' OR assignee_id IS NOT NULL),
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_defects__project_id_key_num ON defects (project_id, key_num);
CREATE UNIQUE INDEX ux_defects__project_id_key ON defects (project_id, key);
CREATE INDEX ix_defects__project_status_severity ON defects (project_id, status, severity);
CREATE INDEX ix_defects__assignee_status ON defects (assignee_id, status);
CREATE INDEX ix_defects__found_in_release ON defects (found_in_release_id);
CREATE INDEX ix_defects__folder_id ON defects (folder_id);
CREATE INDEX ix_defects__search_vector ON defects USING gin (search_vector);
CREATE INDEX ix_defects__title_trgm ON defects USING gin (title gin_trgm_ops);

CREATE TABLE defect_links (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  defect_id        uuid NOT NULL,
  result_id        uuid,
  run_id           uuid,
  step_id          uuid REFERENCES test_case_steps(id),
  test_case_id     uuid,
  requirement_id   uuid,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  CHECK (result_id IS NOT NULL OR test_case_id IS NOT NULL OR requirement_id IS NOT NULL),
  CHECK ((result_id IS NULL) = (run_id IS NULL)),
  FOREIGN KEY (project_id, defect_id) REFERENCES defects (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, result_id) REFERENCES test_results (project_id, id),
  FOREIGN KEY (project_id, run_id) REFERENCES test_runs (project_id, id),
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id),
  FOREIGN KEY (project_id, requirement_id) REFERENCES requirements (project_id, id)
);
CREATE UNIQUE INDEX ux_defect_links__target ON defect_links (
  defect_id, coalesce(result_id, tcms_nil_uuid()), coalesce(test_case_id, tcms_nil_uuid()),
  coalesce(requirement_id, tcms_nil_uuid()));
CREATE INDEX ix_defect_links__result_id ON defect_links (result_id);
CREATE INDEX ix_defect_links__run_id ON defect_links (run_id);
CREATE INDEX ix_defect_links__test_case_id ON defect_links (test_case_id);
CREATE INDEX ix_defect_links__requirement_id ON defect_links (requirement_id);

CREATE TABLE defect_status_history (                             -- append-only
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  defect_id        uuid NOT NULL REFERENCES defects(id),
  from_status      defect_status,
  to_status        defect_status NOT NULL,
  note             text CHECK (char_length(note) <= 20000),
  changed_by       uuid NOT NULL,
  changed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_defect_status_history__defect_changed ON defect_status_history (defect_id, changed_at);

CREATE TABLE defect_watchers (
  defect_id uuid NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
  user_id   uuid NOT NULL REFERENCES users(id),
  PRIMARY KEY (defect_id, user_id)
);

-- ---------------------------------------------------------------------------
-- 3.8 Platform
-- ---------------------------------------------------------------------------
CREATE TABLE comments (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  entity_type     text NOT NULL CHECK (entity_type IN ('test_case','test_case_version','test_result','test_run',
                                                       'defect','requirement','test_plan','test_cycle')),
  entity_id       uuid NOT NULL,
  body            text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 10000),
  mentions        uuid[] NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid NOT NULL,
  edited_at       timestamptz,
  deleted_at      timestamptz,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE INDEX ix_comments__entity ON comments (entity_type, entity_id, created_at);

CREATE TABLE attachments (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  object_key      text NOT NULL,
  file_name       text NOT NULL CHECK (char_length(file_name) BETWEEN 1 AND 255),
  content_type    text NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
  sha256          bytea NOT NULL,
  uploaded_by     uuid NOT NULL,
  uploaded_at     timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_attachments__object_key ON attachments (object_key);

CREATE TABLE attachment_links (
  id              uuid PRIMARY KEY,
  attachment_id   uuid NOT NULL REFERENCES attachments(id),
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  entity_type     text NOT NULL CHECK (entity_type IN ('test_case','test_case_version','test_case_step','test_result',
                                                       'test_step_result','test_run','defect','requirement',
                                                       'test_plan','test_cycle','comment')),
  entity_id       uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid
);
CREATE UNIQUE INDEX ux_attachment_links__target ON attachment_links (attachment_id, entity_type, entity_id);
CREATE INDEX ix_attachment_links__entity ON attachment_links (entity_type, entity_id);

CREATE TABLE notifications (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id),
  user_id         uuid NOT NULL REFERENCES users(id),
  project_id      uuid REFERENCES projects(id),
  type            text NOT NULL,
  entity_type     text,
  entity_id       uuid,
  payload         jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  read_at         timestamptz
);
CREATE INDEX ix_notifications__user_unread ON notifications (user_id, read_at, created_at DESC);

CREATE TABLE saved_views (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  owner_id        uuid NOT NULL REFERENCES users(id),
  entity_type     text NOT NULL,
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  visibility      view_visibility NOT NULL DEFAULT 'private',
  definition      jsonb NOT NULL,
  is_default      boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      uuid,
  row_version     integer NOT NULL DEFAULT 1,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_saved_views__owner_name ON saved_views (project_id, owner_id, entity_type, lower(name));

CREATE TABLE audit_events (                                      -- append-only
  id              uuid PRIMARY KEY,
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  organization_id uuid NOT NULL,
  project_id      uuid,
  actor_type      actor_type NOT NULL,
  actor_id        uuid,
  actor_display   text,
  action          text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
  entity_type     text NOT NULL,
  entity_id       uuid,
  entity_key      text,
  changes         jsonb,
  context         jsonb NOT NULL DEFAULT '{}',
  summary         text,
  prev_hash       bytea,
  hash            bytea
);
CREATE INDEX ix_audit_events__org_occurred ON audit_events (organization_id, occurred_at DESC);
CREATE INDEX ix_audit_events__project_occurred ON audit_events (project_id, occurred_at DESC);
CREATE INDEX ix_audit_events__entity ON audit_events (entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_audit_events__actor ON audit_events (actor_id, occurred_at DESC);
CREATE INDEX ix_audit_events__action ON audit_events (action);

CREATE TABLE jobs (
  id              uuid PRIMARY KEY,
  organization_id uuid,
  type            text NOT NULL,
  payload         jsonb NOT NULL DEFAULT '{}',
  status          job_status NOT NULL DEFAULT 'queued',
  run_at          timestamptz NOT NULL DEFAULT now(),
  attempts        integer NOT NULL DEFAULT 0,
  max_attempts    integer NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
  last_error      text,
  locked_by       text,
  locked_at       timestamptz,
  dedupe_key      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz
);
CREATE INDEX ix_jobs__queue ON jobs (run_at) WHERE status = 'queued';
CREATE INDEX ix_jobs__running_locked ON jobs (locked_at) WHERE status = 'running';
CREATE UNIQUE INDEX ux_jobs__dedupe_key ON jobs (dedupe_key)
  WHERE dedupe_key IS NOT NULL AND status IN ('queued','running');

CREATE TABLE data_transfers (
  id                 uuid PRIMARY KEY,
  organization_id    uuid NOT NULL,
  project_id         uuid NOT NULL,
  kind               transfer_kind NOT NULL,
  entity             text NOT NULL,
  status             transfer_status NOT NULL,
  format             text NOT NULL CHECK (format IN ('csv','xlsx')),
  source_object_key  text,
  result_object_key  text,
  options            jsonb NOT NULL DEFAULT '{}',
  summary            jsonb NOT NULL DEFAULT '{}',
  errors             jsonb NOT NULL DEFAULT '[]',
  created_by         uuid NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  finished_at        timestamptz,
  expires_at         timestamptz,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE INDEX ix_data_transfers__project_created ON data_transfers (project_id, created_at DESC);

CREATE TABLE metric_snapshots (
  id              uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id      uuid NOT NULL,
  release_id      uuid REFERENCES releases(id),
  cycle_id        uuid REFERENCES test_cycles(id),
  day             date NOT NULL,
  counters        jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_metric_snapshots__scope_day ON metric_snapshots (
  project_id, coalesce(release_id, tcms_nil_uuid()), coalesce(cycle_id, tcms_nil_uuid()), day);

CREATE TABLE idempotency_keys (
  principal_id     uuid NOT NULL,
  key              text NOT NULL CHECK (char_length(key) BETWEEN 1 AND 200),
  endpoint         text NOT NULL,
  request_hash     bytea NOT NULL,
  response_status  integer NOT NULL,
  response_body    jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (principal_id, key)
);
CREATE INDEX ix_idempotency_keys__created_at ON idempotency_keys (created_at);

-- ---------------------------------------------------------------------------
-- 4. Integrity triggers and functions
-- Deletions of immutable rows are allowed only when executed as tcms_owner, i.e. inside the
-- SECURITY DEFINER function purge_test_case() or a maintenance session. A session GUC is NOT used:
-- the app role could set it itself.
-- ---------------------------------------------------------------------------
CREATE FUNCTION tcms_is_maintenance() RETURNS boolean LANGUAGE sql STABLE
  AS $$ SELECT current_user = 'tcms_owner' $$;

CREATE FUNCTION tcms_append_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND tcms_is_maintenance() THEN
    RETURN OLD;                                -- retention purge by maintenance role
  END IF;
  RAISE EXCEPTION 'immutable_record: % on %', TG_OP, TG_TABLE_NAME USING ERRCODE = 'P0001';
END $$;

CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION tcms_append_only_guard();
CREATE TRIGGER trg_defect_status_history_append_only BEFORE UPDATE OR DELETE ON defect_status_history
  FOR EACH ROW EXECUTE FUNCTION tcms_append_only_guard();
CREATE TRIGGER trg_release_decisions_append_only BEFORE UPDATE OR DELETE ON release_decisions
  FOR EACH ROW EXECUTE FUNCTION tcms_append_only_guard();

-- Versions: content immutable; submission fields may change; approval fields set once (NULL → value).
CREATE FUNCTION tcms_test_case_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF tcms_is_maintenance() THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'immutable_record: delete test_case_versions %', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF (NEW.id, NEW.organization_id, NEW.project_id, NEW.test_case_id, NEW.version_no, NEW.format, NEW.title,
      NEW.description, NEW.preconditions, NEW.test_data, NEW.expected_result, NEW.postconditions, NEW.text_body,
      NEW.change_note, NEW.content_hash, NEW.created_by, NEW.created_at)
     IS DISTINCT FROM
     (OLD.id, OLD.organization_id, OLD.project_id, OLD.test_case_id, OLD.version_no, OLD.format, OLD.title,
      OLD.description, OLD.preconditions, OLD.test_data, OLD.expected_result, OLD.postconditions, OLD.text_body,
      OLD.change_note, OLD.content_hash, OLD.created_by, OLD.created_at) THEN
    RAISE EXCEPTION 'immutable_record: content of test_case_versions %', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF OLD.approved_at IS NOT NULL AND
     (NEW.approved_at, NEW.approved_by, NEW.approval_mode) IS DISTINCT FROM
     (OLD.approved_at, OLD.approved_by, OLD.approval_mode) THEN
    RAISE EXCEPTION 'immutable_record: approval of test_case_versions % already set', OLD.id USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_test_case_versions_guard BEFORE UPDATE OR DELETE ON test_case_versions
  FOR EACH ROW EXECUTE FUNCTION tcms_test_case_versions_guard();

CREATE FUNCTION tcms_test_case_steps_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND tcms_is_maintenance() THEN RETURN OLD; END IF;
  RAISE EXCEPTION 'immutable_record: % on test_case_steps', TG_OP USING ERRCODE = 'P0001';
END $$;
CREATE TRIGGER trg_test_case_steps_guard BEFORE UPDATE OR DELETE ON test_case_steps
  FOR EACH ROW EXECUTE FUNCTION tcms_test_case_steps_guard();

-- Results: a final attempt can never change or be deleted (BR-06). Draft → final is allowed.
CREATE FUNCTION tcms_test_results_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state = 'final' THEN
    RAISE EXCEPTION 'immutable_record: final result %', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.run_id, NEW.attempt_no, NEW.project_id, NEW.organization_id)
       IS DISTINCT FROM (OLD.run_id, OLD.attempt_no, OLD.project_id, OLD.organization_id) THEN
    RAISE EXCEPTION 'immutable_record: identity of result %', OLD.id USING ERRCODE = 'P0001';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER trg_test_results_guard BEFORE UPDATE OR DELETE ON test_results
  FOR EACH ROW EXECUTE FUNCTION tcms_test_results_guard();

CREATE FUNCTION tcms_test_step_results_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_state result_state;
BEGIN
  SELECT state INTO parent_state FROM test_results
   WHERE id = CASE WHEN TG_OP = 'INSERT' THEN NEW.result_id ELSE OLD.result_id END;
  IF parent_state = 'final' THEN
    RAISE EXCEPTION 'immutable_record: step results of final result' USING ERRCODE = 'P0001';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER trg_test_step_results_guard BEFORE INSERT OR UPDATE OR DELETE ON test_step_results
  FOR EACH ROW EXECUTE FUNCTION tcms_test_step_results_guard();

-- A run's pinned version must belong to the run's case (cross-project integrity is covered by composite FKs).
CREATE FUNCTION tcms_test_runs_version_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM test_case_versions v
                  WHERE v.id = NEW.test_case_version_id AND v.test_case_id = NEW.test_case_id) THEN
    RAISE EXCEPTION 'integrity: version % does not belong to case %', NEW.test_case_version_id, NEW.test_case_id
      USING ERRCODE = 'P0002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_test_runs_version_check BEFORE INSERT OR UPDATE OF test_case_version_id, test_case_id ON test_runs
  FOR EACH ROW EXECUTE FUNCTION tcms_test_runs_version_check();

-- A step result's step must belong to the version pinned by its run.
CREATE FUNCTION tcms_test_step_results_step_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM test_results r JOIN test_runs ru ON ru.id = r.run_id
                   JOIN test_case_steps s ON s.version_id = ru.test_case_version_id
                  WHERE r.id = NEW.result_id AND s.id = NEW.step_id) THEN
    RAISE EXCEPTION 'integrity: step % is not part of the pinned version', NEW.step_id USING ERRCODE = 'P0002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_test_step_results_step_check BEFORE INSERT ON test_step_results
  FOR EACH ROW EXECUTE FUNCTION tcms_test_step_results_step_check();

-- BR-14: hard delete only for never-run cases; executed with owner rights.
CREATE FUNCTION purge_test_case(p_case_id uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM test_runs WHERE test_case_id = p_case_id) THEN
    RAISE EXCEPTION 'case_has_runs: %', p_case_id USING ERRCODE = 'P0003';
  END IF;
  IF EXISTS (SELECT 1 FROM defect_links WHERE test_case_id = p_case_id) THEN
    DELETE FROM defect_links WHERE test_case_id = p_case_id AND result_id IS NULL AND requirement_id IS NULL;
  END IF;
  DELETE FROM test_plan_cases WHERE test_case_id = p_case_id;
  UPDATE test_cases SET latest_version_id = NULL, approved_version_id = NULL WHERE id = p_case_id;
  DELETE FROM test_cases WHERE id = p_case_id;   -- cascades to versions, steps, tags, links, keys
END $$;

-- ---------------------------------------------------------------------------
-- Privileges (docs/05 §4 "Database roles")
-- ---------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION purge_test_case(uuid) FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO tcms_app, tcms_readonly;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tcms_app;
REVOKE UPDATE, DELETE ON audit_events, defect_status_history, release_decisions FROM tcms_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tcms_app;
GRANT EXECUTE ON FUNCTION purge_test_case(uuid) TO tcms_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tcms_readonly;

COMMIT;
