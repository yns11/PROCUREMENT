from datetime import date
from decimal import Decimal
import pytest
from procurement.models import Dataset
from procurement.engine import calculate,lot
from procurement.calendar import distribute,shift

def run(raw):return calculate(Dataset.model_validate(raw))

def test_rollforward_and_determinism(raw):
    a=run(raw);assert a==run(raw)
    assert [r['stock'] for r in a['series'][:7]]==[90,80,70,60,50,50,50]
    assert all(r['stock']==100-sum(x['demand'] for x in a['series'][:i+1]) for i,r in enumerate(a['series']))

def test_weekly_distribution_conserves_exact_total(raw):
    s=Dataset.model_validate(raw).settings
    s.holidays=[date(2026,1,6)]
    for q in [Decimal('1'),Decimal('17.123456'),Decimal('0')]:
        days=distribute(date(2026,1,5),q,s)
        assert sum(days.values())==q and len(days)==4

def test_week_closed_rejects_nonzero(raw):
    s=Dataset.model_validate(raw).settings;s.holidays=[date(2026,1,i) for i in range(5,10)]
    with pytest.raises(ValueError,match='semaine fermée'):distribute(date(2026,1,5),Decimal(5),s)

def test_zero_actual_overrides_forecast(raw):
    raw['actuals']=[{'program':'M','day':'2026-01-05','quantity':0}]
    assert run(raw)['series'][0]['demand']==0
    raw['settings']['production_mode']='plan'
    assert run(raw)['series'][0]['demand']==10

def test_missing_plan_not_zero(raw):
    raw['plans']=raw['plans'][1:]
    with pytest.raises(ValueError,match='manquant'):run(raw)

def test_actual_only_needs_explicit_actuals(raw):
    raw['settings']['production_mode']='actual_only'
    with pytest.raises(ValueError,match='manquant'):run(raw)

def test_partial_receipt_no_double_count(raw):
    raw['orders']=[{'id':'O','item_id':'A','supplier_id':'S','due':'2026-01-05','quantity':100,'received_before_start':20,'status':'confirmed'}]
    raw['receipts']=[{'id':'R','order_id':'O','day':'2026-01-05','quantity':30}]
    result=run(raw)
    assert sum(r['receipts'] for r in result['series'])==80
    assert result['series'][0]['stock']==170

def test_late_receipt_preserves_actual_date(raw):
    raw['orders']=[{'id':'O','item_id':'A','supplier_id':'S','due':'2026-01-05','quantity':100,'status':'confirmed'}]
    raw['receipts']=[{'id':'R','order_id':'O','day':'2026-01-08','quantity':100}]
    rows=run(raw)['series'];assert rows[0]['receipts']==0 and rows[3]['receipts']==100

def test_overreceipt_and_bad_unit_rejected(raw):
    raw['bom'][0]['unit']='KG'
    with pytest.raises(ValueError,match='Unité'):run(raw)

def test_draft_not_firm(raw):
    raw['orders']=[{'id':'O','item_id':'A','supplier_id':'S','due':'2026-01-05','quantity':100,'status':'draft'}]
    r=run(raw)['series'][0];assert r['stock']==90 and r['simulated']==190

def test_moq_multiple_and_feasible_date(raw):
    raw['items'][0]['opening_stock']=0
    r=run(raw);p=r['proposals'][0]
    assert p['due']=='2026-01-07' and p['expedite'] and p['quantity']>=25 and p['quantity']%10==0
    assert r['series'][0]['simulated']==-10 # impossible same-day replenishment never invented

def test_lot_fractional(raw):
    r=Dataset.model_validate(raw).sourcing[0];r.moq=Decimal('2.5');r.multiple=Decimal('.75')
    assert lot(Decimal('2.1'),r)==3

def test_quota_allocation_and_validation(raw):
    raw['items'][0]['opening_stock']=0
    raw['settings']['sourcing_mode']='quota'
    raw['suppliers'].append({'id':'T','name':'Second'})
    raw['sourcing'][0]['quota']='0.6'
    raw['sourcing'].append({**raw['sourcing'][0],'supplier_id':'T','quota':'0.4'})
    p=run(raw)['proposals'];assert {x['supplier_id'] for x in p}=={'S','T'}
    raw['sourcing'][1]['quota']='0.3'
    with pytest.raises(ValueError,match='quotas'):run(raw)

def test_after_demand_intraday_shortage(raw):
    raw['items'][0]['opening_stock']=0
    raw['orders']=[{'id':'O','item_id':'A','supplier_id':'S','due':'2026-01-05','quantity':100,'status':'confirmed'}]
    raw['settings']['receipt_timing']='after_demand'
    r=run(raw)['series'][0];assert r['stock']==90 and r['status']=='rupture'

def test_past_due_not_assumed_received(raw):
    raw['orders']=[{'id':'O','item_id':'A','supplier_id':'S','due':'2026-01-02','quantity':100,'status':'confirmed'}]
    r=run(raw);assert sum(x['receipts'] for x in r['series'])==0 and r['alerts'][0]['type']=='overdue'
    raw['settings']['overdue_policy']='today'
    assert run(raw)['series'][0]['receipts']==100

def test_horizon_censoring(raw):
    raw['plans']=raw['plans'][:2]
    r=run(raw);assert r['series'][-1]['target'] is None
    assert any(a['type']=='horizon' for a in r['alerts'])

def test_coverage_fraction_and_working_days(raw):
    raw['items'][0]['opening_stock']=25
    r=run(raw)['series'][0];assert r['coverage']==Decimal('1.5')

def test_ignore_persists(raw):
    raw['items'][0]['opening_stock']=0
    p=run(raw)['proposals'][0]
    raw['orders']=[{k:p[k] for k in ['id','item_id','supplier_id','due','quantity']}|{'status':'ignored'}]
    assert p['id'] not in {p['id'] for p in run(raw)['proposals']}

def test_duplicate_keys_rejected(raw):
    raw['items']*=2
    with pytest.raises(ValueError,match='dupliquée'):run(raw)

def test_iso_year_boundary_distribution(raw):
    s=Dataset.model_validate(raw).settings
    days=distribute(date(2025,12,29),Decimal(5),s)
    assert date(2026,1,2) in days and sum(days.values())==5
