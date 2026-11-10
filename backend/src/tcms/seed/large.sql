-- Large seeds (TM-4, docs/08 §3; M7 D16, M8 D12): one project with {cases} cases and {attempts} runs
-- (`large`: twice year one; `xlarge`: 10× year one) for timing dashboards, readiness, reports and k6. Bulk SQL instead of services (services would take hours for 500k attempts);
-- every row satisfies the schema's constraints and triggers. Parameters: :org, :pid, :key, :owner,
-- :env, :users (uuid[]). Run in one transaction by `tcms seed --profile large`.
SET LOCAL statement_timeout = 0;
SET CONSTRAINTS ALL DEFERRED;

-- Folders: 20 areas × 10 modules × 5 suites (1,220).
CREATE TEMP TABLE l_root ON COMMIT DROP AS SELECT gen_random_uuid() AS id, i FROM generate_series(1, 20) i;
INSERT INTO folders (id, organization_id, project_id, parent_id, name, position, path, depth)
SELECT id, :org, :pid, NULL, 'Area ' || i, i, '/' || id || '/', 1 FROM l_root;
CREATE TEMP TABLE l_mid ON COMMIT DROP AS
  SELECT gen_random_uuid() AS id, r.id AS parent, '/' || r.id || '/' AS ppath, r.i, j
  FROM l_root r, generate_series(1, 10) j;
INSERT INTO folders (id, organization_id, project_id, parent_id, name, position, path, depth)
SELECT id, :org, :pid, parent, 'Module ' || i || '.' || j, j, ppath || id || '/', 2 FROM l_mid;
CREATE TEMP TABLE l_leaf ON COMMIT DROP AS
  SELECT gen_random_uuid() AS id, m.id AS parent, m.ppath || m.id || '/' AS ppath, m.i, m.j, k,
         row_number() OVER () - 1 AS n
  FROM l_mid m, generate_series(1, 5) k;
INSERT INTO folders (id, organization_id, project_id, parent_id, name, position, path, depth)
SELECT id, :org, :pid, parent, 'Suite ' || i || '.' || j || '.' || k, k, ppath || id || '/', 3 FROM l_leaf;

-- {cases} approved cases with one version each; every fifth is tagged regression, every third automated.
CREATE TEMP TABLE l_case ON COMMIT DROP AS
  SELECT gen_random_uuid() AS id, gen_random_uuid() AS vid, k FROM generate_series(1, {cases}) k;
INSERT INTO test_cases (id, organization_id, project_id, key_num, key, folder_id, title, format, type, priority,
                        status, owner_id, automation_status, latest_version_id, approved_version_id,
                        latest_version_no)
SELECT c.id, :org, :pid, c.k, :key || '-TC-' || c.k, f.id, 'Generated case ' || c.k, 'steps',
       (ARRAY['functional', 'integration', 'api', 'ui'])[1 + c.k % 4]::case_type,
       (ARRAY['critical', 'high', 'medium', 'medium', 'low'])[1 + c.k % 5]::priority_level,
       'approved', :owner, CASE WHEN c.k % 3 = 0 THEN 'automated' ELSE 'manual' END::automation_status,
       c.vid, c.vid, 1
FROM l_case c JOIN l_leaf f ON f.n = c.k % 1000;
INSERT INTO test_case_versions (id, organization_id, project_id, test_case_id, version_no, format, title,
                                content_hash, created_by, approval_mode, approved_at)
SELECT vid, :org, :pid, id, 1, 'steps', 'Generated case ' || k, sha256(convert_to('case ' || k, 'UTF8')),
       :owner, 'auto', now()
FROM l_case;
INSERT INTO tags (id, organization_id, project_id, name, is_system)
SELECT gen_random_uuid(), :org, :pid, 'regression', true
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE project_id = :pid AND name = 'regression');
INSERT INTO test_case_tags (test_case_id, tag_id)
SELECT c.id, t.id FROM l_case c, tags t WHERE t.project_id = :pid AND t.name = 'regression' AND c.k % 5 = 0;
UPDATE folders f SET case_count = x.n
FROM (SELECT folder_id, count(*) AS n FROM test_cases WHERE project_id = :pid GROUP BY folder_id) x
WHERE f.id = x.folder_id;

-- {releases} releases (the last 3 active, the rest released), {cycles_per_release} cycles each, over the last 100 days.
CREATE TEMP TABLE l_rel ON COMMIT DROP AS SELECT gen_random_uuid() AS id, i FROM generate_series(1, {releases}) i;
INSERT INTO releases (id, organization_id, project_id, name, status, start_date, target_date, released_at)
SELECT id, :org, :pid, 'Load release ' || i,
       CASE WHEN i <= {released} THEN 'released' ELSE 'active' END::release_status,
       current_date - (100 - i * {day_step}), current_date - (99 - i * {day_step}),
       CASE WHEN i <= {released} THEN now() - make_interval(days => 99 - i * {day_step}) END
FROM l_rel;
CREATE TEMP TABLE l_cyc ON COMMIT DROP AS
  SELECT gen_random_uuid() AS id, r.id AS release_id, r.i, j, (r.i - 1) * {cycles_per_release} + j AS n
  FROM l_rel r, generate_series(1, {cycles_per_release}) j;
INSERT INTO test_cycles (id, organization_id, project_id, key_num, key, name, release_id, environment_id, status,
                         owner_id, start_date, due_date, started_at, closed_at, closed_by)
SELECT c.id, :org, :pid, c.n, :key || '-CY-' || c.n, 'Load cycle ' || c.n, c.release_id, :env,
       CASE WHEN c.i <= {released} THEN 'closed' ELSE 'active' END::cycle_status, :owner,
       current_date - (100 - c.i * {day_step}), current_date - (99 - c.i * {day_step}), now() - make_interval(days => 100 - c.i * {day_step}),
       CASE WHEN c.i <= {released} THEN now() - make_interval(days => 99 - c.i * {day_step}) END,
       CASE WHEN c.i <= {released} THEN CAST(:owner AS uuid) END
FROM l_cyc c;

-- 250 runs per cycle, each with one final attempt (70 % passed, 15 failed, 5 blocked,
-- 5 skipped, 5 N/A); open releases keep a fifth of their runs not run. Each cycle takes 250 different cases.
CREATE TEMP TABLE l_run ON COMMIT DROP AS
  SELECT gen_random_uuid() AS id, gen_random_uuid() AS result_id, c.id AS cycle_id, c.i, g.rj AS j,
         lc.id AS case_id, lc.vid,
         (CAST(:users AS uuid[]))[1 + (c.n + g.rj) % cardinality(CAST(:users AS uuid[]))] AS assignee,
         CASE WHEN c.i > {released} AND g.rj % 5 = 0 THEN NULL
              ELSE (ARRAY['passed', 'passed', 'passed', 'passed', 'passed', 'passed', 'passed', 'passed',
                          'passed', 'passed', 'passed', 'passed', 'passed', 'passed', 'failed', 'failed',
                          'failed', 'blocked', 'skipped', 'not_applicable'])[1 + (c.n * 7 + g.rj) % 20] END AS status,
         now() - make_interval(days => 100 - c.i * {day_step}, mins => g.rj) AS finished_at
  FROM l_cyc c
  CROSS JOIN generate_series(1, 250) AS g(rj)
  JOIN l_case lc ON lc.k = 1 + (c.n * 50 + g.rj * {stride}) % {cases};
INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position,
                       assignee_id, status, latest_result_id)
SELECT id, :org, :pid, cycle_id, case_id, vid, j, assignee, coalesce(status, 'not_run')::run_status,
       CASE WHEN status IS NOT NULL THEN result_id END
FROM l_run;
INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, state, status, source, executed_by,
                          started_at, finished_at, environment_id, skipped_steps, reason)
SELECT result_id, :org, :pid, id, 1, 'final', status::result_status, 'manual', assignee,
       finished_at - interval '5 minutes', finished_at, :env, 0,
       CASE WHEN status IN ('blocked', 'skipped', 'not_applicable') THEN 'Load seed' END
FROM l_run WHERE status IS NOT NULL;

-- {bug_links} bug links on failed attempts ({bug_refs} distinct references).
INSERT INTO bug_links (id, organization_id, project_id, reference, reference_norm, test_case_id, run_id, result_id,
                       created_at, created_by)
SELECT gen_random_uuid(), :org, :pid, 'LOAD-' || (n % {bug_refs}), 'LOAD-' || (n % {bug_refs}), case_id, id, result_id,
       finished_at, assignee
FROM (SELECT r.*, row_number() OVER (ORDER BY r.cycle_id, r.j) AS n FROM l_run r WHERE r.status = 'failed') f
WHERE n <= {bug_links};

-- {requirements} requirement references; nine in ten are linked to three cases each.
CREATE TEMP TABLE l_req ON COMMIT DROP AS SELECT gen_random_uuid() AS id, i FROM generate_series(1, {requirements}) i;
INSERT INTO requirement_refs (id, organization_id, project_id, reference, reference_norm, title)
SELECT id, :org, :pid, 'REQ-' || i, 'REQ-' || i, 'Generated requirement ' || i FROM l_req;
INSERT INTO requirement_ref_cases (ref_id, test_case_id, organization_id, project_id)
SELECT q.id, c.id, :org, :pid FROM l_req q JOIN l_case c ON c.k BETWEEN q.i * 15 AND q.i * 15 + 2 WHERE q.i % 10 <> 0;

INSERT INTO key_sequences (project_id, entity, next_value) VALUES (:pid, 'test_case', {cases} + 1), (:pid, 'test_cycle', {releases} * {cycles_per_release} + 1)
ON CONFLICT (project_id, entity) DO UPDATE SET next_value = GREATEST(key_sequences.next_value, EXCLUDED.next_value);
