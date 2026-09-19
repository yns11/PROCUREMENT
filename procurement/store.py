"""Atomic optimistic concurrency and immutable revision history (Postgres in production)."""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Text, select, update
from sqlalchemy.exc import IntegrityError

metadata=MetaData()
scenarios=Table('procurement_scenarios',metadata,
    Column('id',String(36),primary_key=True),Column('owner',String(254),nullable=False,index=True),
    Column('name',String(120),nullable=False),Column('version',Integer,nullable=False),
    Column('data',Text,nullable=False),Column('source',String(40),nullable=False),Column('updated_at',String(40),nullable=False))
revisions=Table('procurement_revisions',metadata,
    Column('scenario_id',String(36),primary_key=True),Column('version',Integer,primary_key=True),
    Column('actor',String(254),nullable=False),Column('reason',Text,nullable=False),
    Column('name',String(120),nullable=False),Column('data',Text,nullable=False),Column('created_at',String(40),nullable=False))

class Conflict(Exception):pass
class NotFound(Exception):pass

def now():return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self,url):
        if url == 'lakebase':
            from databricks.sdk import WorkspaceClient
            client=WorkspaceClient()
            target=URL.create('postgresql+psycopg',username=os.environ['PGUSER'],host=os.environ['PGHOST'],port=int(os.getenv('PGPORT','5432')),database=os.environ['PGDATABASE'],query={'sslmode':'require'})
            self.engine=create_engine(target,pool_pre_ping=True,pool_recycle=2700,pool_size=5,max_overflow=5)
            @event.listens_for(self.engine,'do_connect')
            def fresh_credential(dialect,connection_record,args,params):
                params['password']=client.postgres.generate_database_credential(endpoint=os.environ['LAKEBASE_ENDPOINT']).token
        else:
            args={'check_same_thread':False,'timeout':20} if url.startswith('sqlite') else {'connect_timeout':15}
            self.engine=create_engine(url,connect_args=args,pool_pre_ping=True,pool_recycle=2700)
    def initialize(self):metadata.create_all(self.engine)
    def list(self,actor):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(select(scenarios.c.id,scenarios.c.name,scenarios.c.version,scenarios.c.source,scenarios.c.updated_at).where(scenarios.c.owner==actor).order_by(scenarios.c.updated_at.desc())).mappings()]
    def get(self,id,actor):
        with self.engine.connect() as c:
            r=c.execute(select(scenarios).where(scenarios.c.id==id,scenarios.c.owner==actor)).mappings().first()
            if r is None:raise NotFound()
            result=dict(r); result['data']=json.loads(result['data']); return result
    def create(self,actor,name,data,source='manual'):
        id=str(uuid4());stamp=now();payload=data.model_dump_json()
        with self.engine.begin() as c:
            c.execute(scenarios.insert().values(id=id,owner=actor,name=name,version=1,data=payload,source=source,updated_at=stamp))
            c.execute(revisions.insert().values(scenario_id=id,version=1,actor=actor,reason='Création '+source,name=name,data=payload,created_at=stamp))
        return self.get(id,actor)
    def save(self,id,actor,name,data,version,reason):
        stamp=now();payload=data.model_dump_json()
        with self.engine.begin() as c:
            r=c.execute(update(scenarios).where(scenarios.c.id==id,scenarios.c.owner==actor,scenarios.c.version==version).values(name=name,data=payload,version=version+1,updated_at=stamp))
            if r.rowcount!=1:raise Conflict('Version obsolète ou scénario inaccessible. Rechargez avant de modifier.')
            c.execute(revisions.insert().values(scenario_id=id,version=version+1,actor=actor,reason=reason,name=name,data=payload,created_at=stamp))
        return self.get(id,actor)
    def history(self,id,actor):
        self.get(id,actor)
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(select(revisions.c.version,revisions.c.actor,revisions.c.reason,revisions.c.created_at).where(revisions.c.scenario_id==id).order_by(revisions.c.version.desc())).mappings()]
    def revision(self,id,actor,version):
        self.get(id,actor)
        with self.engine.connect() as c:
            r=c.execute(select(revisions).where(revisions.c.scenario_id==id,revisions.c.version==version)).mappings().first()
            if not r:raise NotFound()
            return json.loads(r['data'])
