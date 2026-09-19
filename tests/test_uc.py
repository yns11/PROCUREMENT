import json
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from procurement.models import Dataset
from procurement.uc import read_snapshot
from scripts.snapshot_rows import rows

@pytest.fixture
def warehouse(monkeypatch,raw):
    from databricks import sql
    import databricks.sdk.core
    monkeypatch.setenv('PROCUREMENT_UC_VIEW','test.app.snapshot')
    monkeypatch.setenv('DATABRICKS_WAREHOUSE_ID','warehouse1')
    monkeypatch.setattr(databricks.sdk.core,'Config',lambda:SimpleNamespace(host='https://test.databricks.com',authenticate=lambda:{}))
    cursor=MagicMock();connection=MagicMock();connection.__enter__.return_value.cursor.return_value.__enter__.return_value=cursor
    monkeypatch.setattr(sql,'connect',lambda **kwargs:connection)
    stamp=datetime.now(timezone.utc).isoformat()
    records=list(rows(Dataset.model_validate(raw),'batch1',stamp))
    cursor.fetchall.return_value=[tuple(r[k] for k in ['entity','payload','batch_id','as_of']) for r in records]
    return cursor

def test_uc_valid_batch(warehouse):
    data,batch=read_snapshot();assert batch=='batch1' and len(data.items)==1
    assert 'LIMIT 100001' in warehouse.execute.call_args.args[0]

def test_uc_rejects_mixed_batches(warehouse):
    r=list(warehouse.fetchall.return_value[0]);r[2]='other';warehouse.fetchall.return_value[0]=tuple(r)
    with pytest.raises(ValueError,match='incohérent'):read_snapshot()

def test_uc_rejects_old_snapshot(warehouse):
    stamp=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    warehouse.fetchall.return_value=[(*r[:3],stamp) for r in warehouse.fetchall.return_value]
    with pytest.raises(ValueError,match='périmé'):read_snapshot()

def test_uc_rejects_sql_identifier(monkeypatch,warehouse):
    monkeypatch.setenv('PROCUREMENT_UC_VIEW','a.b.c; DROP TABLE x')
    with pytest.raises(ValueError,match='catalog.schema.view'):read_snapshot()
    warehouse.execute.assert_not_called()
