"""Entirely synthetic seed; no source workbook data or supplier identifiers."""
from datetime import date,timedelta
from .models import Dataset

def dataset(start=None):
    start=start or date.today(); monday=start-timedelta(days=start.weekday())
    data={'settings':{'start':str(start),'horizon':56},'items':[], 'suppliers':[{'id':'SUP-A','name':'Atelier Nord'},{'id':'SUP-B','name':'Industries Horizon'},{'id':'SUP-C','name':'Métal & Composants'}], 'sourcing':[], 'bom':[], 'plans':[], 'orders':[], 'receipts':[], 'actuals':[], 'adjustments':[]}
    labels=['Connecteur de puissance','Fil de bobinage','Tôle stator','Résine isolante','Joint de carter','Roulement rotor','Busbar assemblé','Couvercle moteur']
    for i,label in enumerate(labels):
        key=f'DEMO-{i+1:03d}';sup=f'SUP-{chr(65+i%3)}'
        data['items'].append({'id':key,'name':label,'unit':'PCE','planner':'Équipe démonstration','opening_stock':[320,2400,8500,600,22000,3400,980,6700][i],'safety_stock':100,'min_days':2,'target_days':7,'max_days':20})
        data['sourcing'].append({'item_id':key,'supplier_id':sup,'moq':200,'multiple':100,'lead_days':3+i%4})
        data['bom'].append({'program':'Moteur Alpha' if i%2==0 else 'Moteur Beta','item_id':key,'quantity':1,'unit':'PCE'})
        if i%3==0:data['orders'].append({'id':f'CMD-{i+1:03d}','item_id':key,'supplier_id':sup,'due':str(start+timedelta(days=4)),'quantity':1200,'status':'confirmed'})
    for p,base in [('Moteur Alpha',1500),('Moteur Beta',2000)]:
        for w in range(32):data['plans'].append({'program':p,'week':str(monday+timedelta(weeks=w)),'quantity':base+(w%4)*100})
    return Dataset.model_validate(data)
