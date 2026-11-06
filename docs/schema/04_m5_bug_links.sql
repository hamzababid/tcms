-- 04_m5_bug_links.sql — M5 bug links (ADR-023; docs/05 §3.6; docs/02 §8).
-- Applied by Alembic migration 0003 after 03_m1_additions.sql. Run as tcms_owner.
-- Bugs live in each team's tracker; Assay stores references to them. The baseline defect tables
-- (defects, defect_links, defect_status_history, defect_watchers) stay unused.
BEGIN;

CREATE TABLE bug_links (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  reference        text NOT NULL CHECK (char_length(reference) BETWEEN 1 AND 100 AND reference = btrim(reference)),
  reference_norm   text NOT NULL CHECK (reference_norm = upper(reference)),
  url              text CHECK (char_length(url) <= 2000 AND url ~* '^https?://'),
  title            text CHECK (char_length(title) <= 255),
  test_case_id     uuid NOT NULL,
  run_id           uuid,
  result_id        uuid,
  step_id          uuid REFERENCES test_case_steps(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  updated_by       uuid,
  row_version      integer NOT NULL DEFAULT 1,
  CHECK ((result_id IS NULL) = (run_id IS NULL)),
  CHECK (step_id IS NULL OR result_id IS NOT NULL),
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id),
  FOREIGN KEY (project_id, test_case_id) REFERENCES test_cases (project_id, id),
  FOREIGN KEY (project_id, run_id) REFERENCES test_runs (project_id, id),
  FOREIGN KEY (project_id, result_id) REFERENCES test_results (project_id, id)
);
CREATE UNIQUE INDEX ux_bug_links__target ON bug_links (
  project_id, reference_norm, test_case_id, coalesce(result_id, tcms_nil_uuid()), coalesce(step_id, tcms_nil_uuid()));
CREATE INDEX ix_bug_links__project_reference ON bug_links (project_id, reference_norm);
CREATE INDEX ix_bug_links__run_id ON bug_links (run_id);
CREATE INDEX ix_bug_links__result_id ON bug_links (result_id);
CREATE INDEX ix_bug_links__test_case_id ON bug_links (test_case_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON bug_links TO tcms_app;
GRANT SELECT ON bug_links TO tcms_readonly;

-- Project option renamed (docs/02 §4.2): require_defect_for_failure → require_bug_link_for_failure.
UPDATE projects
   SET settings = (settings - 'require_defect_for_failure')
                  || jsonb_build_object('require_bug_link_for_failure', settings -> 'require_defect_for_failure')
 WHERE settings ? 'require_defect_for_failure';

-- Readiness rule max_open_defects → max_failed with the same threshold (docs/02 §11.4).
UPDATE test_plans
   SET exit_rules = (
         SELECT jsonb_agg(CASE WHEN r ->> 'type' = 'max_open_defects'
                               THEN jsonb_build_object('type', 'max_failed', 'threshold', r -> 'threshold')
                               ELSE r END ORDER BY ord)
           FROM jsonb_array_elements(exit_rules) WITH ORDINALITY AS e(r, ord))
 WHERE exit_rules @> '[{"type": "max_open_defects"}]';

COMMIT;
