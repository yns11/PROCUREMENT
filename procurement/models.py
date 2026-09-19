"""Validated canonical contract. Quantities use Decimal, dates are plant-local dates."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Key = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[\w .:/@+\-]+$')]
Qty = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
SignedQty = Annotated[Decimal, Field(max_digits=18, decimal_places=6, allow_inf_nan=False)]

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Item(Model):
    id: Key
    name: Annotated[str, Field(min_length=1, max_length=180)]
    unit: Key = 'PCE'
    planner: Key = 'Équipe'
    opening_stock: SignedQty = Decimal(0)
    safety_stock: Qty = Decimal(0)
    min_days: int = Field(default=2, ge=0, le=90)
    target_days: int = Field(default=10, ge=0, le=180)
    max_days: int = Field(default=30, ge=1, le=365)
    @model_validator(mode='after')
    def thresholds(self):
        if not self.min_days <= self.target_days <= self.max_days:
            raise ValueError('Seuils attendus : minimum ≤ cible ≤ maximum')
        return self

class Supplier(Model):
    id: Key
    name: Annotated[str, Field(min_length=1, max_length=180)]

class Sourcing(Model):
    item_id: Key
    supplier_id: Key
    moq: Qty = Decimal(0)
    multiple: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)] = Decimal(1)
    lead_days: int = Field(default=5, ge=0, le=365)
    quota: Annotated[Decimal, Field(ge=0, le=1, decimal_places=6)] = Decimal(1)
    priority: int = Field(default=1, ge=1, le=100)
    # PLA is deliberately explicit, never guessed to mean MOQ or pack multiple.
    pla: str = Field(default='', max_length=100)

class Bom(Model):
    program: Key
    item_id: Key
    quantity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]
    unit: Key = 'PCE'

class Plan(Model):
    program: Key
    week: date
    quantity: Qty
    @model_validator(mode='after')
    def monday(self):
        if self.week.weekday() != 0: raise ValueError('La semaine PDP doit être un lundi ISO')
        return self

class Actual(Model):
    program: Key
    day: date
    quantity: Qty

class Order(Model):
    id: Key
    item_id: Key
    supplier_id: Key
    due: date
    quantity: Qty
    received_before_start: Qty = Decimal(0)
    status: Literal['confirmed','draft','ignored','cancelled'] = 'draft'
    message_type: Literal['MANUAL','DELFOR','DELJIT'] = 'MANUAL'
    @model_validator(mode='after')
    def received(self):
        if self.received_before_start > self.quantity: raise ValueError('Reçu supérieur à la commande')
        return self

class Receipt(Model):
    id: Key
    order_id: Key
    day: date
    quantity: Qty

class Adjustment(Model):
    id: Key
    item_id: Key
    day: date
    quantity: SignedQty
    reason: Annotated[str, Field(min_length=3, max_length=500)]

class Settings(Model):
    start: date
    horizon: int = Field(default=56, ge=7, le=366)
    workdays: list[int] = Field(default_factory=lambda: [0,1,2,3,4], min_length=1, max_length=7)
    holidays: list[date] = Field(default_factory=list, max_length=1000)
    lead_calendar: Literal['working','calendar'] = 'working'
    coverage_calendar: Literal['working','calendar'] = 'working'
    production_mode: Literal['plan','actual_preferred','actual_only'] = 'actual_preferred'
    sourcing_mode: Literal['priority','quota'] = 'priority'
    receipt_timing: Literal['before_demand','after_demand'] = 'before_demand'
    overdue_policy: Literal['exclude','today'] = 'exclude'
    @model_validator(mode='after')
    def days(self):
        if len(set(self.workdays)) != len(self.workdays) or any(d not in range(7) for d in self.workdays):
            raise ValueError('Calendrier : jours uniques entre 0 et 6')
        return self

class Dataset(Model):
    settings: Settings
    items: list[Item] = Field(default_factory=list, max_length=2000)
    suppliers: list[Supplier] = Field(default_factory=list, max_length=1000)
    sourcing: list[Sourcing] = Field(default_factory=list, max_length=10000)
    bom: list[Bom] = Field(default_factory=list, max_length=20000)
    plans: list[Plan] = Field(default_factory=list, max_length=50000)
    actuals: list[Actual] = Field(default_factory=list, max_length=50000)
    orders: list[Order] = Field(default_factory=list, max_length=50000)
    receipts: list[Receipt] = Field(default_factory=list, max_length=50000)
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=50000)

    @model_validator(mode='after')
    def integrity(self):
        specs = {'items':lambda x:x.id,'suppliers':lambda x:x.id,
                 'sourcing':lambda x:(x.item_id,x.supplier_id),'bom':lambda x:(x.program,x.item_id),
                 'plans':lambda x:(x.program,x.week),'actuals':lambda x:(x.program,x.day),
                 'orders':lambda x:x.id,'receipts':lambda x:x.id,'adjustments':lambda x:x.id}
        for table,key in specs.items():
            vals=[key(x) for x in getattr(self,table)]
            if len(vals)!=len(set(vals)): raise ValueError(f'Clé dupliquée dans {table}')
        items={x.id:x for x in self.items}; suppliers={x.id for x in self.suppliers}
        links={(x.item_id,x.supplier_id) for x in self.sourcing}
        programs={x.program for x in self.bom}; orders={x.id:x for x in self.orders}
        for x in [*self.sourcing,*self.bom,*self.orders,*self.adjustments]:
            if x.item_id not in items: raise ValueError(f'Article inconnu : {x.item_id}')
        for x in [*self.sourcing,*self.orders]:
            if x.supplier_id not in suppliers: raise ValueError(f'Fournisseur inconnu : {x.supplier_id}')
        for x in self.orders:
            if (x.item_id,x.supplier_id) not in links: raise ValueError(f'Lien article fournisseur absent : {x.id}')
        for x in self.bom:
            if x.unit.upper()!=items[x.item_id].unit.upper(): raise ValueError(f'Unité incompatible : {x.item_id}')
        for x in [*self.plans,*self.actuals]:
            if x.program not in programs: raise ValueError(f'Programme sans nomenclature : {x.program}')
        totals={k:o.received_before_start for k,o in orders.items()}
        for x in self.receipts:
            if x.order_id not in orders: raise ValueError(f'Commande inconnue : {x.order_id}')
            if x.day<self.settings.start: raise ValueError('Réception antérieure au stock initial : intégrer dans received_before_start')
            if orders[x.order_id].status!='confirmed': raise ValueError('Une réception doit concerner une commande confirmée')
            totals[x.order_id]+=x.quantity
        for k,q in totals.items():
            if q>orders[k].quantity: raise ValueError(f'Surréception non autorisée : {k}')
        for x in self.adjustments:
            if x.day<self.settings.start: raise ValueError('Ajustement déjà inclus dans le stock initial')
        if self.settings.sourcing_mode=='quota':
            for k in items:
                rows=[x for x in self.sourcing if x.item_id==k]
                if rows and sum(x.quota for x in rows)!=Decimal(1):
                    raise ValueError(f'La somme des quotas doit être égale à 1 : {k}')
        return self

class ScenarioCreate(Model):
    name: Annotated[str, Field(min_length=1,max_length=120)]
    data: Dataset

class ScenarioUpdate(ScenarioCreate):
    version: int = Field(ge=1)
    reason: Annotated[str, Field(min_length=3,max_length=500)]
