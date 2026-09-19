"""Generate synthetic canonical UC rows as JSONL for integration development."""
import json
from datetime import datetime,timezone
from procurement.demo import dataset

def rows(data,batch_id,stamp):
    payload=data.model_dump(mode='json')
    for name,values in payload.items():
        for obj in ([values] if name=='settings' else values):
            yield {'entity':name,'payload':json.dumps(obj,ensure_ascii=False),'batch_id':batch_id,'as_of':stamp}

if __name__=='__main__':
    for row in rows(dataset(),'synthetic-v1',datetime.now(timezone.utc).isoformat()):print(json.dumps(row,ensure_ascii=False))
