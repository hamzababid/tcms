-- 05_m6_requirement_refs.sql — M6 requirement references (ADR-024; docs/05 §3.7; docs/02 §10).
-- Applied by Alembic migration 0004 after 04_m5_bug_links.sql. Run as tcms_owner.
-- Requirements live in each team's tool; Assay stores references, links them to cases and plans, and
-- computes coverage. The baseline tables requirements, requirement_case_links and test_plan_requirements
-- stay unused.
BEGIN;

CREATE TABLE requirement_refs (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  reference        text NOT NULL CHECK (char_length(reference) BETWEEN 1 AND 100 AND reference = btrim(reference)),
  reference_norm   text NOT NULL CHECK (reference_norm = upper(reference)),
  url              text CHECK (char_length(url) <= 2000 AND url ~* '^https?://'),
  title            text CHECK (char_length(title) <= 255),
  archived_at      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  updated_by       uuid,
  row_version      integer NOT NULL DEFAULT 1,
  UNIQUE (project_id, id),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_requirement_refs__project_reference ON requirement_refs (project_id, reference_norm);
CREATE INDEX ix_requirement_refs__reference_trgm ON requirement_refs USING gin (reference_norm gin_trgm_ops);
CREATE INDEX ix_requirement_refs__title_trgm ON requirement_refs USING gin (title gin_trgm_ops);

CREATE TABLE requirement_ref_cases (
  ref_id           uuid NOT NULL,
  test_case_id     uuid NOT NULL,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  PRIMARY KEY (ref_id, test_case_id),
  FOREIGN KEY (project_id, ref_id) REFERENCES requirement_refs (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_requirement_ref_cases__test_case_id ON requirement_ref_cases (test_case_id);

CREATE TABLE plan_requirement_refs (
  plan_id          uuid NOT NULL,
  ref_id           uuid NOT NULL,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  PRIMARY KEY (plan_id, ref_id),
  FOREIGN KEY (project_id, plan_id) REFERENCES test_plans (project_id, id) ON DELETE CASCADE,
  FOREIGN KEY (project_id, ref_id) REFERENCES requirement_refs (project_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_plan_requirement_refs__ref_id ON plan_requirement_refs (ref_id);

-- Global search (docs/02 §12): trigram on names that are searched by text.
CREATE INDEX ix_bug_links__reference_trgm ON bug_links USING gin (reference_norm gin_trgm_ops);
CREATE INDEX ix_test_cycles__name_trgm ON test_cycles USING gin (name gin_trgm_ops);
CREATE INDEX ix_test_plans__name_trgm ON test_plans USING gin (name gin_trgm_ops);

GRANT SELECT, INSERT, UPDATE, DELETE ON requirement_refs, requirement_ref_cases, plan_requirement_refs TO tcms_app;
GRANT SELECT ON requirement_refs, requirement_ref_cases, plan_requirement_refs TO tcms_readonly;

COMMIT;
