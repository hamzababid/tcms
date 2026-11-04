-- 00_roles.sql — cluster-level roles. Run once per PostgreSQL cluster as a superuser.
-- Passwords come from the deployment's secret store; the values below are placeholders.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tcms_owner') THEN
    CREATE ROLE tcms_owner LOGIN PASSWORD 'change-me-owner';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tcms_app') THEN
    CREATE ROLE tcms_app LOGIN PASSWORD 'change-me-app';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tcms_readonly') THEN
    CREATE ROLE tcms_readonly LOGIN PASSWORD 'change-me-readonly';
  END IF;
END $$;
-- Then: CREATE DATABASE tcms OWNER tcms_owner;
