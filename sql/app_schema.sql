-- Run in the Lakebase/PostgreSQL SQL editor, not in a Databricks SQL Warehouse.
CREATE TABLE IF NOT EXISTS public.procurement_scenarios (
  id VARCHAR(36) PRIMARY KEY,
  owner VARCHAR(254) NOT NULL,
  name VARCHAR(120) NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  data TEXT NOT NULL,
  source VARCHAR(40) NOT NULL,
  updated_at VARCHAR(40) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_procurement_scenarios_owner ON public.procurement_scenarios(owner);
CREATE TABLE IF NOT EXISTS public.procurement_revisions (
  scenario_id VARCHAR(36) NOT NULL,
  version INTEGER NOT NULL,
  actor VARCHAR(254) NOT NULL,
  reason TEXT NOT NULL,
  name VARCHAR(120) NOT NULL,
  data TEXT NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  PRIMARY KEY (scenario_id, version)
);
-- Replace APP_CLIENT_ID with the actual existing role created when adding the resource.
-- The runtime has no DELETE right and cannot overwrite existing audit rows.
GRANT USAGE ON SCHEMA public TO "APP_CLIENT_ID";
GRANT SELECT, INSERT, UPDATE ON public.procurement_scenarios TO "APP_CLIENT_ID";
GRANT SELECT, INSERT ON public.procurement_revisions TO "APP_CLIENT_ID";
