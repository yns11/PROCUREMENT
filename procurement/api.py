"""HTTP boundary: identity, authorization, validation, persistence and export."""
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
import json
import logging
import os
from typing import Annotated, Literal
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError, Field
from .models import Dataset, ScenarioCreate, ScenarioUpdate, Model, Order
from .engine import calculate
from .store import Store, Conflict, NotFound
from .demo import dataset
from .exchange import export_workbook,read_workbook,read_pdp,MAX_BYTES

log=logging.getLogger(__name__)
STATIC=Path(__file__).parent/'static'

def create_app(database_url=None,mode=None):
    mode=mode or os.getenv('APP_MODE','production')
    if mode not in ('demo','production'):raise RuntimeError('APP_MODE invalide')
    url=database_url or os.getenv('DATABASE_URL') or ('lakebase' if os.getenv('PGHOST') and os.getenv('LAKEBASE_ENDPOINT') else None)
    if mode=='production':
        if not url or (url != 'lakebase' and not url.startswith('postgresql+psycopg://')):
            raise RuntimeError('Production : Lakebase ou DATABASE_URL PostgreSQL durable obligatoire')
        if not os.getenv('DATABRICKS_APP_NAME'):
            raise RuntimeError('Production : application attendue derrière le proxy Databricks Apps')
        if not os.getenv('PROCUREMENT_EDITORS'):
            raise RuntimeError('Production : configurer PROCUREMENT_EDITORS')
    store=Store(url or 'sqlite:///procurement-demo.db')
    @asynccontextmanager
    async def lifespan(app):
        if mode=='demo':store.initialize()
        yield
        store.engine.dispose()
    app=FastAPI(title='Procurement',version='1.0.0',lifespan=lifespan,docs_url='/api/docs',redoc_url=None)
    app.state.store=store
    def actor(request:Request):
        if mode=='demo':return 'demo@local'
        who=request.headers.get('x-forwarded-email','').strip().lower()
        if not who or len(who)>254:raise HTTPException(401,'Identité Databricks absente')
        return who
    def editor(who=Depends(actor)):
        allowed={s.strip().lower() for s in os.getenv('PROCUREMENT_EDITORS','').split(',')}
        if mode!='demo' and who not in allowed:raise HTTPException(403,'Accès en lecture seule')
        return who
    @app.middleware('http')
    async def security(request,call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('x-procurement-request')!='1':return JSONResponse({'detail':'En-tête de requête requis'},status_code=403)
            length=request.headers.get('content-length')
            if length and (not length.isdigit() or int(length)>12*1024*1024):return JSONResponse({'detail':'Requête trop volumineuse'},status_code=413)
        result=await call_next(request)
        result.headers['X-Content-Type-Options']='nosniff'
        result.headers['Referrer-Policy']='same-origin'
        result.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith('/api/'):result.headers['Cache-Control']='no-store'
        return result
    @app.exception_handler(Conflict)
    async def conflict(_,exc):return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(NotFound)
    async def missing(_,exc):return JSONResponse({'detail':'Scénario inaccessible'},status_code=404)
    @app.exception_handler(ValueError)
    async def invalid(_,exc):return JSONResponse({'detail':str(exc)[:2500]},status_code=422)
    @app.get('/health')
    def health():return {'status':'ok','version':'1.0.0'}
    @app.get('/api/me')
    def me(who=Depends(actor)):
        return {'user':who,'mode':mode,'can_edit':mode=='demo' or who in {s.strip().lower() for s in os.getenv('PROCUREMENT_EDITORS','').split(',')},'erp_configured':bool(os.getenv('PROCUREMENT_UC_VIEW'))}
    @app.get('/api/scenarios')
    def listing(who=Depends(actor)):return store.list(who)
    @app.post('/api/demo')
    def seed(who=Depends(editor)):
        if mode!='demo':raise HTTPException(403,'Démonstration désactivée en production')
        return store.create(who,'Portefeuille de démonstration',dataset(),'demo')
    @app.post('/api/scenarios')
    def new(body:ScenarioCreate,who=Depends(editor)):return store.create(who,body.name,body.data)
    @app.get('/api/scenarios/{id}')
    def get(id:str,who=Depends(actor)):return store.get(id,who)
    @app.put('/api/scenarios/{id}')
    def save(id:str,body:ScenarioUpdate,who=Depends(editor)):
        return store.save(id,who,body.name,body.data,body.version,body.reason)
    @app.post('/api/scenarios/{id}/clone')
    def clone(id:str,who=Depends(editor)):
        old=store.get(id,who)
        return store.create(who,(old['name']+' · variante')[:120],Dataset.model_validate(old['data']),old['source'])
    @app.post('/api/scenarios/{id}/calculate')
    def run(id:str,who=Depends(actor)):
        snapshot=store.get(id,who); data=Dataset.model_validate(snapshot['data'])
        if len(data.items)*data.settings.horizon>200000:raise ValueError('Limiter le calcul à 200 000 couples article/jour par portefeuille')
        result=calculate(data)
        return {**result,'scenario_id':id,'version':snapshot['version']}
    @app.get('/api/scenarios/{id}/history')
    def history(id:str,who=Depends(actor)):return store.history(id,who)
    class Restore(Model):
        version:int=Field(ge=1)
        target_version:int=Field(ge=1)
    @app.post('/api/scenarios/{id}/restore')
    def restore(id:str,body:Restore,who=Depends(editor)):
        snapshot=store.get(id,who); previous=Dataset.model_validate(store.revision(id,who,body.target_version))
        return store.save(id,who,snapshot['name'],previous,body.version,f'Restauration version {body.target_version}')
    class Decision(Model):
        version:int=Field(ge=1)
        proposal_id:str
        action:Literal['accept','ignore']
        quantity:Annotated[str,Field(max_length=30)]|None=None
        due:date|None=None
    @app.post('/api/scenarios/{id}/decision')
    def decision(id:str,body:Decision,who=Depends(editor)):
        snapshot=store.get(id,who)
        if snapshot['version']!=body.version:raise Conflict('Les données ont changé. Recalculez les propositions.')
        data=Dataset.model_validate(snapshot['data']);result=calculate(data)
        p=next((p for p in result['proposals'] if p['id']==body.proposal_id),None)
        if not p:raise Conflict('Proposition obsolète. Recalculez.')
        rule=next(r for r in data.sourcing if (r.item_id,r.supplier_id)==(p['item_id'],p['supplier_id']))
        order=Order(id=p['id'],item_id=p['item_id'],supplier_id=p['supplier_id'],due=body.due or p['due'],quantity=body.quantity or p['quantity'],status='draft' if body.action=='accept' else 'ignored')
        if body.action=='accept' and (order.quantity<rule.moq or order.quantity%rule.multiple!=0 or order.quantity<=0):raise ValueError('Respecter MOQ et multiple fournisseur')
        if order.due<data.settings.start:raise ValueError('Date de proposition antérieure au scénario')
        data.orders.append(order);data=Dataset.model_validate(data.model_dump())
        return store.save(id,who,snapshot['name'],data,body.version,'Proposition '+body.action+' '+body.proposal_id)
    @app.get('/api/scenarios/{id}/export')
    def export(id:str,items:str='',supplier:str='',granularity:Literal['day','week','month']='day',who=Depends(actor)):
        snapshot=store.get(id,who);data=Dataset.model_validate(snapshot['data'])
        ids=set(items.split(',')) if items else None
        if supplier:
            supplier_items={r.item_id for r in data.sourcing if r.supplier_id==supplier}
            ids=supplier_items if ids is None else ids&supplier_items
        content=export_workbook(data,calculate(data),ids,granularity)
        return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="procurement-simulation.xlsx"'})
    @app.post('/api/import')
    async def import_file(file:UploadFile=File(),name:str=Form('Simulation importée'),who=Depends(editor)):
        content=await file.read(MAX_BYTES+1)
        data=read_workbook(content)
        checked=ScenarioCreate(name=name,data=data)
        return store.create(who,checked.name,data,'excel')
    @app.post('/api/scenarios/{id}/pdp')
    async def pdp(id:str,file:UploadFile=File(),version:int=Form(),who=Depends(editor)):
        snapshot=store.get(id,who);raw=snapshot['data'];raw['plans']=read_pdp(await file.read(MAX_BYTES+1))
        data=Dataset.model_validate(raw)
        return store.save(id,who,snapshot['name'],data,version,'Remplacement du PDP depuis CSV')
    @app.post('/api/erp')
    def erp(who=Depends(editor)):
        from .uc import read_snapshot
        try:data,batch=read_snapshot()
        except ValueError:raise
        except Exception:
            log.exception('Lecture ERP impossible')
            raise HTTPException(503,'Lecture ERP indisponible. Vérifier la ressource Warehouse, les droits UC et les journaux.')
        return store.create(who,'Snapshot ERP '+date.today().isoformat(),data,('erp:'+batch)[:40])
    @app.get('/')
    def index():return FileResponse(STATIC/'index.html')
    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app

# Test code uses create_app with explicit demo configuration.
if os.getenv('PROCUREMENT_SKIP_APP')!='1':app=create_app()
