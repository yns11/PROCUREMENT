"""Pure, deterministic one-level MRP. No database, UI or wall-clock dependency."""
from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
from .models import Dataset
from .calendar import DAY, distribute, working, shift, roll

ZERO=Decimal(0)

def lot(quantity, rule):
    return (max(quantity,rule.moq)/rule.multiple).to_integral_value(rounding=ROUND_CEILING)*rule.multiple

def calculate(data:Dataset)->dict:
    s=data.settings
    if len(data.items)*s.horizon>200000:raise ValueError('Limiter le calcul à 200 000 couples article/jour')
    start=s.start; end=start+(s.horizon-1)*DAY
    # Demand padding is required for cover and order-up-to near the visible horizon.
    padding=max([x.max_days for x in data.items]+[30])*7+14
    dates=[start+i*DAY for i in range(s.horizon+padding)]
    last=dates[-1]; index={d:i for i,d in enumerate(dates)}
    production={}; valid_until={}; missing=[]; alerts=[]
    programs=sorted({b.program for b in data.bom})
    plans={(p.program,p.week):p for p in data.plans}
    actuals={(p.program,p.day):p.quantity for p in data.actuals}
    for program in programs:
        for p in (p for p in data.plans if p.program==program):
            for d,q in distribute(p.week,p.quantity,s).items():production[program,d]=q
        first_missing=None
        for d in dates:
            key=(program,d)
            if s.production_mode!='plan' and key in actuals:production[key]=actuals[key]
            elif s.production_mode=='actual_only':
                if working(d,s):production.pop(key,None)
            if not working(d,s) and key not in actuals:production[key]=ZERO
            if key not in production and first_missing is None:first_missing=d
        valid_until[program]=(first_missing-DAY) if first_missing else last
        if first_missing and first_missing<=end:missing.append(f'{program} : {first_missing}')
    if missing:raise ValueError('PDP/réalisé manquant (zéro explicite requis) : '+', '.join(missing[:8]))
    needs=defaultdict(lambda:defaultdict(Decimal))
    for b in data.bom:
        for d in dates:
            if (b.program,d) in production:needs[b.item_id][d]+=production[b.program,d]*b.quantity
    firm=defaultdict(lambda:defaultdict(Decimal)); drafts=defaultdict(lambda:defaultdict(Decimal))
    adjustments=defaultdict(lambda:defaultdict(Decimal)); receipt_sum=defaultdict(Decimal)
    orders={x.id:x for x in data.orders}
    for r in data.receipts:
        receipt_sum[r.order_id]+=r.quantity
        firm[orders[r.order_id].item_id][r.day]+=r.quantity
    for o in data.orders:
        if o.status not in ('confirmed','draft'):continue
        remaining=o.quantity-o.received_before_start-receipt_sum[o.id]
        if not remaining:continue
        due=o.due
        if due<start:
            alerts.append({'item_id':o.item_id,'type':'overdue','date':str(due),'message':f'Commande {o.id} en retard : {remaining} restant'})
            if s.overdue_policy=='exclude':continue
            due=roll(start,s)
        (firm if o.status=='confirmed' else drafts)[o.item_id][due]+=remaining
    for a in data.adjustments:adjustments[a.item_id][a.day]+=a.quantity
    proposals=[]; rows=[]; summary=[]
    for item in sorted(data.items,key=lambda x:x.id):
        related={b.program for b in data.bom if b.item_id==item.id}
        known=min([valid_until[p] for p in related],default=last)
        if not related:alerts.append({'item_id':item.id,'type':'no_bom','date':str(start),'message':'Article sans besoin nomenclature'})
        demand=[needs[item.id][d] for d in dates]
        prefix=[ZERO]
        for q in demand:prefix.append(prefix[-1]+q)
        cover_indices=[i for i,d in enumerate(dates) if s.coverage_calendar=='calendar' or working(d,s)]
        def target(i,n):
            # Coverage windows start strictly after the end-of-day stock.
            pos=bisect_right(cover_indices,i); ids=cover_indices[pos:pos+n]
            if n and (len(ids)<n or dates[ids[-1]]>known):return None
            if not ids:return item.safety_stock
            return item.safety_stock+prefix[ids[-1]+1]-prefix[i+1]
        def coverage(i,stock):
            if stock<0:return (ZERO,False)
            stop=min(index.get(known,len(dates)-1),len(dates)-1)
            if stop<=i:return (None,True)
            # Find first future demand exhausting stock; zero-demand days remain meaningful.
            j=bisect_right(prefix,prefix[i+1]+stock,lo=i+2,hi=stop+2)-1
            if j>=stop+1:
                return (Decimal(bisect_right(cover_indices,stop)-bisect_right(cover_indices,i)),True)
            whole=Decimal(bisect_right(cover_indices,j-1)-bisect_right(cover_indices,i))
            fraction=(stock-(prefix[j]-prefix[i+1]))/demand[j] if demand[j] else ZERO
            return (whole+fraction,False)
        rules=sorted([r for r in data.sourcing if r.item_id==item.id],key=lambda r:(r.priority,r.supplier_id))
        if not rules:alerts.append({'item_id':item.id,'type':'no_supplier','date':str(start),'message':'Aucune source fournisseur : propositions impossibles'})
        if s.sourcing_mode=='priority':rules=rules[:1]
        else:rules=[r for r in rules if r.quota>0]
        generated=defaultdict(Decimal); stock=item.opening_stock; sim=stock; first=None; lows=0; highs=0; itemrows=[]
        for i,d in enumerate(dates[:s.horizon]):
            qty=demand[i]; incoming=firm[item.id][d]; draft=drafts[item.id][d]; adjust=adjustments[item.id][d]
            before=stock+adjust-(qty if s.receipt_timing=='after_demand' else ZERO)
            stock+=incoming+adjust-qty
            sim+=incoming+draft+generated[d]+adjust-qty
            low=target(i,item.min_days); goal=target(i,item.target_days); high=target(i,item.max_days)
            available=sim
            # Outstanding receipts/proposals through the latest feasible lead date prevent repeated expediting.
            arrivals=[max(roll(d,s),roll(shift(roll(start,s),r.lead_days,s,s.lead_calendar),s)) for r in rules]
            check=max(arrivals,default=d)
            for future in dates[i+1:min(len(dates),(check-start).days+1)]:
                available+=firm[item.id][future]+drafts[item.id][future]+generated[future]+adjustments[item.id][future]-needs[item.id][future]
            check_i=index.get(check); order_target=target(check_i,item.target_days) if check_i is not None else None
            if low is not None and sim<low and order_target is not None and available<order_target:
                shortage=order_target-available
                for r,arrival in zip(rules,arrivals):
                    q=lot(shortage*(r.quota if s.sourcing_mode=='quota' else 1),r)
                    if q<=0:continue
                    release=roll(shift(arrival,-r.lead_days,s,s.lead_calendar),s,-1)
                    identity=f'{item.id}|{r.supplier_id}|{d}|{arrival}|{q}'
                    proposal={'id':'MRP-'+sha256(identity.encode()).hexdigest()[:16],'item_id':item.id,'supplier_id':r.supplier_id,'quantity':q,'need_date':str(d),'due':str(arrival),'release':str(release),'expedite':arrival>d,'status':'proposed'}
                    if proposal['id'] in orders:continue
                    proposals.append(proposal); generated[arrival]+=q
                    if arrival==d:sim+=q
            cov,bounded=coverage(i,stock)
            critical=stock<0 or (s.receipt_timing=='after_demand' and before<0)
            status='rupture' if critical else ('low' if low is not None and stock<low else ('overstock' if high is not None and stock>high else 'ok'))
            if critical and first is None:first=str(d)
            lows+=status=='low';highs+=status=='overstock'
            row={'item_id':item.id,'date':str(d),'demand':qty,'receipts':incoming,'draft_receipts':draft,'adjustment':adjust,'stock':stock,'simulated':sim,'target':goal,'coverage':cov,'coverage_censored':bounded,'status':status}
            rows.append(row);itemrows.append(row)
        summary.append({'item_id':item.id,'name':item.name,'unit':item.unit,'planner':item.planner,'opening_stock':item.opening_stock,'first_shortage':first,'low_days':lows,'overstock_days':highs,'min_stock':min(r['stock'] for r in itemrows),'coverage':itemrows[0]['coverage'],'coverage_censored':itemrows[0]['coverage_censored'],'status':'rupture' if first else ('low' if lows else ('overstock' if highs else 'ok'))})
        if any(r['target'] is None for r in itemrows):alerts.append({'item_id':item.id,'type':'horizon','date':str(known),'message':'PDP futur insuffisant pour calculer toute la couverture cible'})
    return {'summary':summary,'series':rows,'proposals':proposals,'alerts':alerts,'engine_version':'1.0.0'}
