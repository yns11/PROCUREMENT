"""Calendar operations shared by production distribution and purchase planning."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from .models import Settings

DAY=timedelta(days=1)

def working(day: date, settings: Settings) -> bool:
    return day.weekday() in settings.workdays and day not in settings.holidays

def shift(day: date, count: int, settings: Settings, kind: str='working') -> date:
    step=1 if count>=0 else -1
    left=abs(count)
    while left:
        day+=step*DAY
        if kind=='calendar' or working(day,settings): left-=1
    return day

def roll(day:date, settings:Settings, direction:int=1)->date:
    for _ in range(1500):
        if working(day,settings):return day
        day+=direction*DAY
    raise ValueError('Calendrier sans jour ouvert accessible')

def distribute(week:date, qty:Decimal, settings:Settings)->dict:
    days=[week+i*DAY for i in range(7) if working(week+i*DAY,settings)]
    if not days:
        if qty:raise ValueError(f'PDP non nul sur semaine fermée : {week}')
        return {}
    # Preserve the exact weekly total, including fractional production and explicit zero.
    share=(qty/len(days)).quantize(Decimal('.000001'),rounding=ROUND_DOWN)
    return {d:(share if i<len(days)-1 else qty-share*(len(days)-1)) for i,d in enumerate(days)}
