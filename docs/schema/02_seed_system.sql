-- 02_seed_system.sql — system roles and permissions (docs/02 §3.2). Idempotent.
-- Org-level permissions (org.*, project.create) are implied by organization_members.is_org_admin
-- and the qa_managers_can_create_projects setting; they are not attached to project roles.
BEGIN;
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000001', NULL, 'qa_manager', 'QA Manager', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000001';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000001', 'project.view'),
  ('00000000-0000-7000-8000-000000000001', 'project.configure'),
  ('00000000-0000-7000-8000-000000000001', 'project.members.manage'),
  ('00000000-0000-7000-8000-000000000001', 'project.audit.view'),
  ('00000000-0000-7000-8000-000000000001', 'folder.manage'),
  ('00000000-0000-7000-8000-000000000001', 'testcase.create'),
  ('00000000-0000-7000-8000-000000000001', 'testcase.edit'),
  ('00000000-0000-7000-8000-000000000001', 'testcase.approve'),
  ('00000000-0000-7000-8000-000000000001', 'testcase.archive'),
  ('00000000-0000-7000-8000-000000000001', 'testcase.delete'),
  ('00000000-0000-7000-8000-000000000001', 'plan.manage'),
  ('00000000-0000-7000-8000-000000000001', 'cycle.manage'),
  ('00000000-0000-7000-8000-000000000001', 'cycle.reopen'),
  ('00000000-0000-7000-8000-000000000001', 'run.execute'),
  ('00000000-0000-7000-8000-000000000001', 'defect.create'),
  ('00000000-0000-7000-8000-000000000001', 'defect.edit'),
  ('00000000-0000-7000-8000-000000000001', 'defect.transition.any'),
  ('00000000-0000-7000-8000-000000000001', 'requirement.manage'),
  ('00000000-0000-7000-8000-000000000001', 'requirement.link'),
  ('00000000-0000-7000-8000-000000000001', 'release.manage'),
  ('00000000-0000-7000-8000-000000000001', 'data.export'),
  ('00000000-0000-7000-8000-000000000001', 'comment.create');
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000002', NULL, 'qa_lead', 'QA Lead', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000002';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000002', 'project.view'),
  ('00000000-0000-7000-8000-000000000002', 'folder.manage'),
  ('00000000-0000-7000-8000-000000000002', 'testcase.create'),
  ('00000000-0000-7000-8000-000000000002', 'testcase.edit'),
  ('00000000-0000-7000-8000-000000000002', 'testcase.approve'),
  ('00000000-0000-7000-8000-000000000002', 'testcase.archive'),
  ('00000000-0000-7000-8000-000000000002', 'plan.manage'),
  ('00000000-0000-7000-8000-000000000002', 'cycle.manage'),
  ('00000000-0000-7000-8000-000000000002', 'run.execute'),
  ('00000000-0000-7000-8000-000000000002', 'defect.create'),
  ('00000000-0000-7000-8000-000000000002', 'defect.edit'),
  ('00000000-0000-7000-8000-000000000002', 'defect.transition.any'),
  ('00000000-0000-7000-8000-000000000002', 'requirement.link'),
  ('00000000-0000-7000-8000-000000000002', 'data.export'),
  ('00000000-0000-7000-8000-000000000002', 'comment.create');
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000003', NULL, 'qa_engineer', 'QA Engineer', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000003';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000003', 'project.view'),
  ('00000000-0000-7000-8000-000000000003', 'testcase.create'),
  ('00000000-0000-7000-8000-000000000003', 'testcase.edit'),
  ('00000000-0000-7000-8000-000000000003', 'run.execute'),
  ('00000000-0000-7000-8000-000000000003', 'defect.create'),
  ('00000000-0000-7000-8000-000000000003', 'defect.edit'),
  ('00000000-0000-7000-8000-000000000003', 'defect.transition.verify'),
  ('00000000-0000-7000-8000-000000000003', 'requirement.link'),
  ('00000000-0000-7000-8000-000000000003', 'data.export'),
  ('00000000-0000-7000-8000-000000000003', 'comment.create');
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000004', NULL, 'developer', 'Developer', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000004';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000004', 'project.view'),
  ('00000000-0000-7000-8000-000000000004', 'defect.create'),
  ('00000000-0000-7000-8000-000000000004', 'defect.edit'),
  ('00000000-0000-7000-8000-000000000004', 'defect.transition.dev'),
  ('00000000-0000-7000-8000-000000000004', 'data.export'),
  ('00000000-0000-7000-8000-000000000004', 'comment.create');
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000005', NULL, 'pm_ba', 'Product Manager / BA', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000005';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000005', 'project.view'),
  ('00000000-0000-7000-8000-000000000005', 'requirement.manage'),
  ('00000000-0000-7000-8000-000000000005', 'requirement.link'),
  ('00000000-0000-7000-8000-000000000005', 'data.export'),
  ('00000000-0000-7000-8000-000000000005', 'comment.create');
INSERT INTO roles (id, organization_id, code, name, is_system) VALUES ('00000000-0000-7000-8000-000000000006', NULL, 'viewer', 'Viewer', true)
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
DELETE FROM role_permissions WHERE role_id = '00000000-0000-7000-8000-000000000006';
INSERT INTO role_permissions (role_id, permission) VALUES
  ('00000000-0000-7000-8000-000000000006', 'project.view'),
  ('00000000-0000-7000-8000-000000000006', 'data.export');
COMMIT;
