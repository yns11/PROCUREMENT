import os
os.environ['PROCUREMENT_SKIP_APP']='1'
import pytest
from datetime import date,timedelta
from procurement.models import Dataset

@pytest.fixture
def raw():
    monday=date(2026,1,5)
    return {'settings':{'start':str(monday),'horizon':14},'items':[{'id':'A','name':'Component','opening_stock':100,'min_days':1,'target_days':3,'max_days':10}], 'suppliers':[{'id':'S','name':'Supplier'}], 'sourcing':[{'item_id':'A','supplier_id':'S','moq':25,'multiple':10,'lead_days':2}], 'bom':[{'program':'M','item_id':'A','quantity':1}], 'plans':[{'program':'M','week':str(monday+timedelta(weeks=w)),'quantity':50} for w in range(20)]}

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from procurement.api import create_app
    app=create_app('sqlite:///'+str(tmp_path/'test.db'),'demo')
    with TestClient(app) as client:
        client.headers['X-Procurement-Request']='1'
        yield client
