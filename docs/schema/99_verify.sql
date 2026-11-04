-- 99_verify.sql — executable checks of the database-level invariants (docs/05 §4).
-- Run as tcms_app against a freshly migrated, empty database. Everything runs in one
-- transaction and is rolled back, so it leaves no data. Prints PASS lines; any failure aborts.
\set ON_ERROR_STOP 1
BEGIN;

CREATE FUNCTION pg_temp.expect_error(q text, pattern text, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM ~* pattern OR SQLSTATE ~* pattern THEN
      RAISE NOTICE 'PASS  %', label;
      RETURN;
    END IF;
    RAISE EXCEPTION 'FAIL  % — unexpected error [%] %', label, SQLSTATE, SQLERRM;
  END;
  RAISE EXCEPTION 'FAIL  % — statement succeeded but should have failed', label;
END $$;

CREATE FUNCTION pg_temp.ok(label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN RAISE NOTICE 'PASS  %', label; END $$;

-- Fixture -------------------------------------------------------------------
INSERT INTO organizations (id, name, slug) VALUES
  ('a0000000-0000-7000-8000-000000000001', 'ACME', 'acme'),
  ('a0000000-0000-7000-8000-000000000002', 'Other', 'other');
INSERT INTO users (id, email, display_name) VALUES
  ('b0000000-0000-7000-8000-000000000001', 'sana@acme.test', 'Sana');
INSERT INTO projects (id, organization_id, key, name) VALUES
  ('c0000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'SPARK', 'SPARK'),
  ('c0000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'HELIOS', 'HELIOS');
INSERT INTO environments (id, organization_id, project_id, name) VALUES
  ('d0000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001', 'QA');
INSERT INTO folders (id, organization_id, project_id, name, path, depth) VALUES
  ('e0000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   'Login', '/e0000000-0000-7000-8000-000000000001/', 1),
  ('e0000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000002',
   'Other', '/e0000000-0000-7000-8000-000000000002/', 1);

-- Case 1 (SPARK) with v1 and v2; case 2 (SPARK) never run; case 3 in HELIOS.
INSERT INTO test_cases (id, organization_id, project_id, key_num, key, folder_id, title, status, owner_id,
                        latest_version_id, approved_version_id) VALUES
  ('f0000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   1, 'SPARK-TC-1', 'e0000000-0000-7000-8000-000000000001', 'Login valid', 'approved', 'b0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000002', '10000000-0000-7000-8000-000000000001'),
  ('f0000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   2, 'SPARK-TC-2', 'e0000000-0000-7000-8000-000000000001', 'Never run', 'draft', 'b0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000003', NULL),
  ('f0000000-0000-7000-8000-000000000003', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000002',
   1, 'HELIOS-TC-1', 'e0000000-0000-7000-8000-000000000002', 'Other project', 'draft', 'b0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000004', NULL);
INSERT INTO test_case_versions (id, organization_id, project_id, test_case_id, version_no, format, title, content_hash,
                                created_by, approved_at, approval_mode) VALUES
  ('10000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   'f0000000-0000-7000-8000-000000000001', 1, 'steps', 'Login valid', '\x01', 'b0000000-0000-7000-8000-000000000001', now(), 'auto'),
  ('10000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   'f0000000-0000-7000-8000-000000000001', 2, 'steps', 'Login valid v2', '\x02', 'b0000000-0000-7000-8000-000000000001', NULL, NULL),
  ('10000000-0000-7000-8000-000000000003', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   'f0000000-0000-7000-8000-000000000002', 1, 'steps', 'Never run', '\x03', 'b0000000-0000-7000-8000-000000000001', NULL, NULL),
  ('10000000-0000-7000-8000-000000000004', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000002',
   'f0000000-0000-7000-8000-000000000003', 1, 'steps', 'Other project', '\x04', 'b0000000-0000-7000-8000-000000000001', NULL, NULL);
INSERT INTO test_case_steps (id, organization_id, project_id, version_id, position, action) VALUES
  ('20000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000001', 1, 'Open page'),
  ('20000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000001', 2, 'Sign in'),
  ('20000000-0000-7000-8000-000000000003', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '10000000-0000-7000-8000-000000000002', 1, 'Open page v2');
SET CONSTRAINTS ALL IMMEDIATE;   -- deferred version FKs resolve here
SELECT pg_temp.ok('deferred FKs between test_cases and test_case_versions resolve in one transaction');
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO test_cycles (id, organization_id, project_id, key_num, key, name, environment_id, owner_id) VALUES
  ('30000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   1, 'SPARK-CY-1', 'Regression 01', 'd0000000-0000-7000-8000-000000000001', 'b0000000-0000-7000-8000-000000000001');
INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position) VALUES
  ('40000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '30000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000001', '10000000-0000-7000-8000-000000000001', 1);

-- BR-12: one active run per case per cycle
SELECT pg_temp.expect_error($q$
  INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '30000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000001', '10000000-0000-7000-8000-000000000001', 2)
$q$, 'ux_test_runs__cycle_case_active', 'BR-12 duplicate active run rejected');

-- Pinned version must belong to the run's case
SELECT pg_temp.expect_error($q$
  INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '30000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000002', '10000000-0000-7000-8000-000000000001', 2)
$q$, 'does not belong to case', 'run cannot pin another case''s version');

-- Cross-project: a SPARK cycle cannot contain a HELIOS case
SELECT pg_temp.expect_error($q$
  INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '30000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000003', '10000000-0000-7000-8000-000000000004', 2)
$q$, '23503', 'cross-project run rejected by composite FK');

-- Draft attempt with step results
INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, executed_by, environment_id) VALUES
  ('50000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '40000000-0000-7000-8000-000000000001', 1, 'b0000000-0000-7000-8000-000000000001', 'd0000000-0000-7000-8000-000000000001');
INSERT INTO test_step_results (id, organization_id, project_id, result_id, step_id, position, status) VALUES
  ('60000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '50000000-0000-7000-8000-000000000001', '20000000-0000-7000-8000-000000000001', 1, 'passed'),
  ('60000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '50000000-0000-7000-8000-000000000001', '20000000-0000-7000-8000-000000000002', 2, 'failed');

-- Step from a different version
SELECT pg_temp.expect_error($q$
  INSERT INTO test_step_results (id, organization_id, project_id, result_id, step_id, position) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '50000000-0000-7000-8000-000000000001', '20000000-0000-7000-8000-000000000003', 3)
$q$, 'not part of the pinned version', 'step result must use a step of the pinned version');

-- BR-07: only one draft per run
SELECT pg_temp.expect_error($q$
  INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, executed_by, environment_id) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '40000000-0000-7000-8000-000000000001', 2, 'b0000000-0000-7000-8000-000000000001', 'd0000000-0000-7000-8000-000000000001')
$q$, 'ux_test_results__run_draft', 'BR-07 second draft rejected');

-- Draft is editable
UPDATE test_step_results SET actual_result = 'Took 9 s' WHERE id = '60000000-0000-7000-8000-000000000002';
SELECT pg_temp.ok('draft step result is editable');

-- BR-10: final blocked without reason rejected
SELECT pg_temp.expect_error($q$
  UPDATE test_results SET state = 'final', status = 'blocked', finished_at = now()
   WHERE id = '50000000-0000-7000-8000-000000000001'
$q$, '23514', 'BR-10 final blocked result requires a reason');

-- Finalize
UPDATE test_results SET state = 'final', status = 'failed', finished_at = now()
 WHERE id = '50000000-0000-7000-8000-000000000001';
UPDATE test_runs SET status = 'failed', latest_result_id = '50000000-0000-7000-8000-000000000001'
 WHERE id = '40000000-0000-7000-8000-000000000001';
SELECT pg_temp.ok('draft finalized');

-- BR-06: final attempt and its step results immutable
SELECT pg_temp.expect_error($q$ UPDATE test_results SET comment = 'edit' WHERE id = '50000000-0000-7000-8000-000000000001' $q$,
  'immutable_record', 'BR-06 final result cannot be updated');
SELECT pg_temp.expect_error($q$ DELETE FROM test_results WHERE id = '50000000-0000-7000-8000-000000000001' $q$,
  'immutable_record', 'BR-06 final result cannot be deleted');
SELECT pg_temp.expect_error($q$ UPDATE test_step_results SET status = 'passed' WHERE id = '60000000-0000-7000-8000-000000000002' $q$,
  'immutable_record', 'BR-06 step result of final result cannot be updated');
SELECT pg_temp.expect_error($q$ DELETE FROM test_step_results WHERE id = '60000000-0000-7000-8000-000000000001' $q$,
  'immutable_record', 'BR-06 step result of final result cannot be deleted');

-- Retest: a new draft is allowed once the previous attempt is final
INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, executed_by, environment_id) VALUES
  ('50000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '40000000-0000-7000-8000-000000000001', 2, 'b0000000-0000-7000-8000-000000000001', 'd0000000-0000-7000-8000-000000000001');
DELETE FROM test_results WHERE id = '50000000-0000-7000-8000-000000000002';
SELECT pg_temp.ok('retest draft can be created and discarded');

-- BR-05: replace run (supersede, then insert new active run at v2)
UPDATE test_runs SET superseded_by_run_id = '40000000-0000-7000-8000-000000000002', superseded_at = now()
 WHERE id = '40000000-0000-7000-8000-000000000001';
INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position) VALUES
  ('40000000-0000-7000-8000-000000000002', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   '30000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000001', '10000000-0000-7000-8000-000000000002', 1);
SET CONSTRAINTS ALL IMMEDIATE;
SELECT pg_temp.ok('BR-05 replace run: superseded run kept, new active run allowed');
SET CONSTRAINTS ALL DEFERRED;

-- BR-01: version content immutable; approval set once
SELECT pg_temp.expect_error($q$ UPDATE test_case_versions SET title = 'changed' WHERE id = '10000000-0000-7000-8000-000000000002' $q$,
  'immutable_record', 'BR-01 version content cannot change');
UPDATE test_case_versions SET submitted_by = 'b0000000-0000-7000-8000-000000000001', submitted_at = now()
 WHERE id = '10000000-0000-7000-8000-000000000002';
UPDATE test_case_versions SET approved_by = 'b0000000-0000-7000-8000-000000000001', approved_at = now(), approval_mode = 'manual'
 WHERE id = '10000000-0000-7000-8000-000000000002';
SELECT pg_temp.ok('version submission and first approval allowed');
SELECT pg_temp.expect_error($q$ UPDATE test_case_versions SET approved_at = now() + interval '1 day'
  WHERE id = '10000000-0000-7000-8000-000000000002' $q$, 'already set', 'approval cannot be changed once set');
SELECT pg_temp.expect_error($q$ DELETE FROM test_case_versions WHERE id = '10000000-0000-7000-8000-000000000003' $q$,
  'immutable_record', 'app role cannot delete versions directly');
SELECT pg_temp.expect_error($q$ UPDATE test_case_steps SET action = 'x' WHERE id = '20000000-0000-7000-8000-000000000001' $q$,
  'immutable_record', 'steps immutable');
-- The old GUC-based bypass must not work for the app role
SET LOCAL tcms.purge = 'on';
SELECT pg_temp.expect_error($q$ DELETE FROM test_case_steps WHERE id = '20000000-0000-7000-8000-000000000003' $q$,
  'immutable_record', 'session setting cannot bypass immutability');

-- BR-14: purge only never-run cases
SELECT pg_temp.expect_error($q$ SELECT purge_test_case('f0000000-0000-7000-8000-000000000001') $q$,
  'case_has_runs', 'BR-14 purge refused for a case with runs');
SELECT purge_test_case('f0000000-0000-7000-8000-000000000002');
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM test_case_versions WHERE test_case_id = 'f0000000-0000-7000-8000-000000000002') THEN
    RAISE EXCEPTION 'FAIL  BR-14 purge left versions behind';
  END IF;
END $$;
SELECT pg_temp.ok('BR-14 never-run case purged with its versions');

-- BR-26: append-only tables
INSERT INTO audit_events (id, organization_id, actor_type, action, entity_type)
VALUES ('70000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'system', 'test_case.created', 'test_case');
SELECT pg_temp.expect_error($q$ UPDATE audit_events SET summary = 'x' $q$, 'permission denied', 'BR-26 audit update denied');
SELECT pg_temp.expect_error($q$ DELETE FROM audit_events $q$, 'permission denied', 'BR-26 audit delete denied');

-- Defect rules
INSERT INTO defects (id, organization_id, project_id, key_num, key, title, steps_to_reproduce, expected_result, actual_result,
                     reporter_id) VALUES
  ('80000000-0000-7000-8000-000000000001', 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
   1, 'SPARK-D-1', 'Login slow', '1. Sign in', 'Under 3 s', '9 s', 'b0000000-0000-7000-8000-000000000001');
SELECT pg_temp.expect_error($q$ UPDATE defects SET status = 'duplicate' WHERE id = '80000000-0000-7000-8000-000000000001' $q$,
  '23514', 'duplicate requires duplicate_of_id');
SELECT pg_temp.expect_error($q$ UPDATE defects SET status = 'assigned' WHERE id = '80000000-0000-7000-8000-000000000001' $q$,
  '23514', 'assigned requires assignee');
INSERT INTO defect_links (id, organization_id, project_id, defect_id, result_id, run_id, step_id, test_case_id)
VALUES (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
        '80000000-0000-7000-8000-000000000001', '50000000-0000-7000-8000-000000000001',
        '40000000-0000-7000-8000-000000000001', '20000000-0000-7000-8000-000000000002', 'f0000000-0000-7000-8000-000000000001');
SELECT pg_temp.expect_error($q$
  INSERT INTO defect_links (id, organization_id, project_id, defect_id, result_id, run_id, test_case_id)
  VALUES (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
          '80000000-0000-7000-8000-000000000001', '50000000-0000-7000-8000-000000000001',
          '40000000-0000-7000-8000-000000000001', 'f0000000-0000-7000-8000-000000000001')
$q$, 'ux_defect_links__target', 'duplicate defect link rejected');
INSERT INTO defect_status_history (id, organization_id, project_id, defect_id, to_status, changed_by)
VALUES (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001',
        '80000000-0000-7000-8000-000000000001', 'open', 'b0000000-0000-7000-8000-000000000001');
SELECT pg_temp.expect_error($q$ DELETE FROM defect_status_history $q$, 'permission denied', 'defect history append-only');

-- Folder rules
SELECT pg_temp.expect_error($q$
  INSERT INTO folders (id, organization_id, project_id, name, path, depth) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001', 'LOGIN', '/x/', 1)
$q$, '23505|23514', 'folder sibling names unique (case-insensitive)');
SELECT pg_temp.expect_error($q$
  INSERT INTO folders (id, organization_id, project_id, name, path, depth) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001', 'a/b', '/x/', 1)
$q$, '23514', 'folder name cannot contain /');

-- Project key format and tenancy
SELECT pg_temp.expect_error($q$ INSERT INTO projects (id, organization_id, key, name) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'spark', 'x') $q$, '23514', 'BR-27 project key format');
SELECT pg_temp.expect_error($q$ INSERT INTO environments (id, organization_id, project_id, name) VALUES
  (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000002', 'c0000000-0000-7000-8000-000000000001', 'Leak') $q$,
  '23503', 'child row cannot claim another organization''s project');

-- Partial-null unique indexes work with the nil-uuid sentinel
INSERT INTO metric_snapshots (id, organization_id, project_id, day, counters)
VALUES (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001', current_date, '{}');
SELECT pg_temp.expect_error($q$ INSERT INTO metric_snapshots (id, organization_id, project_id, day, counters)
  VALUES (gen_random_uuid(), 'a0000000-0000-7000-8000-000000000001', 'c0000000-0000-7000-8000-000000000001', current_date, '{}') $q$,
  'ux_metric_snapshots__scope_day', 'one project-level snapshot per day');

SET CONSTRAINTS ALL IMMEDIATE;
SELECT pg_temp.ok('all deferred constraints satisfied at end');
ROLLBACK;
