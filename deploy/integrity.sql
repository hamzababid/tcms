-- Post-restore integrity checks (docs/ops/deploy.md §Restore, TCMS-141). Read-only; run as tcms_app.
-- Every row must report ok = true. Counts are printed so the drill log can compare them with the source.
\pset footer off
SELECT 'migration head recorded' AS check, count(*) = 1 AS ok, count(*)::text AS detail FROM alembic_version
UNION ALL
SELECT 'organizations present', count(*) > 0, count(*)::text FROM organizations
UNION ALL
SELECT 'every project has its key sequences', count(*) = 0, count(*)::text || ' projects without'
  FROM projects p WHERE NOT EXISTS (SELECT 1 FROM key_sequences k WHERE k.project_id = p.id)
UNION ALL
SELECT 'case keys below their sequence', count(*) = 0, count(*)::text || ' cases ahead of the sequence'
  FROM test_cases c JOIN key_sequences k ON k.project_id = c.project_id AND k.entity = 'test_case'
  WHERE c.key_num >= k.next_value
UNION ALL
SELECT 'every case has its current version', count(*) = 0, count(*)::text || ' cases without'
  FROM test_cases c WHERE NOT EXISTS (SELECT 1 FROM test_case_versions v WHERE v.test_case_id = c.id)
UNION ALL
SELECT 'every run points at an existing version', count(*) = 0, count(*)::text || ' runs without'
  FROM test_runs r WHERE NOT EXISTS (SELECT 1 FROM test_case_versions v WHERE v.id = r.test_case_version_id)
UNION ALL
SELECT 'final results have a status', count(*) = 0, count(*)::text || ' final results without'
  FROM test_results WHERE state = 'final' AND status IS NULL
UNION ALL
SELECT 'audit log is append-only (trigger present)', count(*) = 1, count(*)::text
  FROM pg_trigger WHERE tgname = 'trg_audit_events_append_only'
UNION ALL
SELECT 'attachments recorded', true, count(*)::text || ' attachments, ' ||
  coalesce(sum(size_bytes), 0)::text || ' bytes' FROM attachments WHERE deleted_at IS NULL
UNION ALL
SELECT 'audit events', true, count(*)::text FROM audit_events;
