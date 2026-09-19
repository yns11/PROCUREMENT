-- Template: replace catalog/schema names before execution with an authorized identity.
-- ERP source column mappings are intentionally NOT guessed.
CREATE TABLE IF NOT EXISTS REPLACE_CATALOG.REPLACE_SCHEMA.procurement_snapshot_rows (
  entity STRING NOT NULL,
  payload STRING NOT NULL,
  batch_id STRING NOT NULL,
  as_of TIMESTAMP NOT NULL
) USING DELTA;

-- Publish a single complete batch atomically, e.g. INSERT OVERWRITE the table in one
-- statement from a validated staging batch. Never append mixed batches to this view.
CREATE OR REPLACE VIEW REPLACE_CATALOG.REPLACE_SCHEMA.procurement_snapshot AS
SELECT entity, payload, batch_id, as_of
FROM REPLACE_CATALOG.REPLACE_SCHEMA.procurement_snapshot_rows;

-- Entity values: settings (exactly one), items, suppliers, sourcing, bom, plans,
-- actuals, orders, receipts, adjustments. Payload is one JSON object per row.
-- See docs/04-deploiement.md and scripts.snapshot_rows for the canonical example.
-- Example mapping pattern only (the private ERP column names must be supplied):
-- SELECT 'items' AS entity,
--   to_json(named_struct('id', component_id, 'name', description, 'unit', unit,
--                        'opening_stock', available_quantity,
--                        'min_days', 2, 'target_days', 10, 'max_days', 30)) AS payload,
--   batch_id, as_of
-- FROM validated_inventory_staging;

-- Grant on the application view only, with actual service principal client ID:
-- GRANT USE CATALOG ON CATALOG REPLACE_CATALOG TO `APP_CLIENT_ID`;
-- GRANT USE SCHEMA ON SCHEMA REPLACE_CATALOG.REPLACE_SCHEMA TO `APP_CLIENT_ID`;
-- GRANT SELECT ON VIEW REPLACE_CATALOG.REPLACE_SCHEMA.procurement_snapshot TO `APP_CLIENT_ID`;
