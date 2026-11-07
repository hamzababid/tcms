-- 06_m8_import_mappings.sql — M8 import mapping templates (docs/05 §3.8; docs/02 §15.1; US-151).
-- Applied by Alembic migration 0005 after 05_m6_requirement_refs.sql. Run as tcms_owner.
BEGIN;

CREATE TABLE import_mappings (
  id               uuid PRIMARY KEY,
  organization_id  uuid NOT NULL,
  project_id       uuid NOT NULL,
  entity           text NOT NULL CHECK (entity IN ('test_case', 'requirement')),
  name             text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100 AND name = btrim(name)),
  mapping          jsonb NOT NULL CHECK (jsonb_typeof(mapping) = 'object'),
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  FOREIGN KEY (organization_id, project_id) REFERENCES projects (organization_id, id)
);
CREATE UNIQUE INDEX ux_import_mappings__project_entity_name ON import_mappings (project_id, entity, lower(name));

GRANT SELECT, INSERT, UPDATE, DELETE ON import_mappings TO tcms_app;
GRANT SELECT ON import_mappings TO tcms_readonly;

COMMIT;
