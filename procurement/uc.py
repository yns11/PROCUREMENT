"""Read one published, consistent ERP snapshot via a SQL Warehouse.

The view is an explicit canonical contract, not guessed mappings to private ERP tables.
No SQL supplied by a browser is executed. No ERP write-back is provided.
"""
import json
import os
import re
from datetime import datetime, timezone
from .models import Dataset

ENTITIES=set(Dataset.model_fields)-{'settings'}

def read_snapshot()->tuple[Dataset,str]:
    from databricks import sql
    from databricks.sdk.core import Config
    view=os.environ.get('PROCUREMENT_UC_VIEW','')
    if not re.fullmatch(r'[A-Za-z_][\w]*\.[A-Za-z_][\w]*\.[A-Za-z_][\w]*',view):
        raise ValueError('PROCUREMENT_UC_VIEW doit désigner catalog.schema.view')
    warehouse=os.environ['DATABRICKS_WAREHOUSE_ID']
    if not re.fullmatch(r'[\w-]+',warehouse):raise ValueError('Identifiant Warehouse invalide')
    cfg=Config(); name='.'.join('`'+s+'`' for s in view.split('.'))
    with sql.connect(server_hostname=cfg.host.removeprefix('https://').rstrip('/'),http_path=f'/sql/1.0/warehouses/{warehouse}',credentials_provider=lambda:cfg.authenticate) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT entity, payload, batch_id, as_of FROM {name} LIMIT 100001')
            rows=cursor.fetchall()
    if not rows:raise ValueError('Snapshot ERP vide')
    if len(rows)>100000:raise ValueError('Snapshot trop volumineux : partitionner par portefeuille dans la vue')
    batches={r[2] for r in rows}; stamps={str(r[3]) for r in rows}
    if len(batches)!=1 or None in batches or len(stamps)!=1:raise ValueError('Snapshot ERP incohérent : plusieurs lots ou horodatages')
    stamp=rows[0][3]
    if isinstance(stamp,str):stamp=datetime.fromisoformat(stamp.replace('Z','+00:00'))
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    age=(datetime.now(timezone.utc)-stamp).total_seconds()
    if age < -300 or age>int(os.environ.get('ERP_MAX_AGE_HOURS','24'))*3600:
        raise ValueError('Snapshot ERP périmé ou horodaté dans le futur')
    data={e:[] for e in ENTITIES}; setting_count=0
    for entity,payload,_,_ in rows:
        obj=json.loads(payload)
        if entity=='settings':data['settings']=obj;setting_count+=1
        elif entity in ENTITIES:data[entity].append(obj)
        else:raise ValueError(f'Entité ERP inconnue : {entity}')
    if setting_count!=1:raise ValueError('Une seule ligne settings est requise')
    validated=Dataset.model_validate(data)
    if not validated.items or not validated.bom:raise ValueError('Référentiel ERP incomplet')
    return validated,str(next(iter(batches)))
