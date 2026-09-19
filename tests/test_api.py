import pytest
from procurement.models import Dataset
from procurement.store import Store,Conflict,NotFound

def create(c,raw):
    r=c.post('/api/scenarios',json={'name':'Test','data':raw});assert r.status_code==200,r.text;return r.json()

def test_scenario_lifecycle_and_conflict(client,raw):
    s=create(client,raw);url='/api/scenarios/'+s['id'];body={'name':'Edited','data':s['data'],'version':1,'reason':'Test modification'}
    assert client.put(url,json=body).status_code==200
    assert client.put(url,json=body).status_code==409
    assert len(client.get(url+'/history').json())==2
    assert client.post(url+'/restore',json={'version':2,'target_version':1}).json()['version']==3
    assert client.post(url+'/clone').json()['id']!=s['id']

def test_csrf_guard_and_calculation(client,raw):
    s=create(client,raw);client.headers.pop('X-Procurement-Request')
    assert client.post('/api/demo').status_code==403
    client.headers['X-Procurement-Request']='1'
    r=client.post('/api/scenarios/'+s['id']+'/calculate');assert r.status_code==200 and len(r.json()['series'])==14

def test_decision_is_draft_and_idempotent_by_version(client,raw):
    raw['items'][0]['opening_stock']=0;s=create(client,raw);url='/api/scenarios/'+s['id'];p=client.post(url+'/calculate').json()['proposals'][0]
    payload={'version':1,'proposal_id':p['id'],'action':'accept'}
    r=client.post(url+'/decision',json=payload);assert r.status_code==200,r.text
    assert r.json()['data']['orders'][0]['status']=='draft'
    assert client.post(url+'/decision',json=payload).status_code==409

def test_ownership_and_atomic_audit(tmp_path,raw):
    db=Store('sqlite:///'+str(tmp_path/'d.db'));db.initialize()
    s=db.create('owner','Test',Dataset.model_validate(raw))
    with pytest.raises(NotFound):db.get(s['id'],'other')
    with pytest.raises(Conflict):db.save(s['id'],'other','X',Dataset.model_validate(raw),1,'Denied')
    assert len(db.history(s['id'],'owner'))==1

def test_export_import_api(client,raw):
    s=create(client,raw);r=client.get('/api/scenarios/'+s['id']+'/export?granularity=week')
    assert r.status_code==200,r.text
    imported=client.post('/api/import',files={'file':('simulation.xlsx',r.content)},data={'name':'Reimport'})
    assert imported.status_code==200,imported.text
    assert imported.json()['data']==s['data']

def test_invalid_negative_receipt_rejected(client,raw):
    raw['receipts']=[{'id':'R','order_id':'missing','day':'2026-01-05','quantity':-1}]
    assert client.post('/api/scenarios',json={'name':'Bad','data':raw}).status_code==422

def test_production_refuses_sqlite(monkeypatch):
    from procurement.api import create_app
    with pytest.raises(RuntimeError,match='durable'):create_app('sqlite:///x.db','production')

def test_production_identity_and_editor_gate(monkeypatch):
    from fastapi.testclient import TestClient
    from procurement.api import create_app
    monkeypatch.setenv('DATABRICKS_APP_NAME','test-app')
    monkeypatch.setenv('PROCUREMENT_EDITORS','editor@example.com')
    app=create_app('postgresql+psycopg://unused:unused@localhost/test','production')
    with TestClient(app) as c:
        assert c.get('/api/me').status_code==401
        c.headers.update({'X-Forwarded-Email':'reader@example.com','X-Procurement-Request':'1'})
        assert c.get('/api/me').json()['can_edit'] is False
        assert c.post('/api/demo').status_code==403
        c.headers['X-Forwarded-Email']='EDITOR@example.com'
        assert c.get('/api/me').json()['can_edit'] is True
        assert c.post('/api/demo').status_code==403 # real environment cannot seed demo
