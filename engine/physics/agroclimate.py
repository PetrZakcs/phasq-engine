"""
Agroklimatické indexy: growing degree days, mrazová rizika, srážkový
deficit. Fáze B "dokončovacího" plánu pro zemědělský vertikál
(viz docs/ADR-004-agroclimate.md) — staví na engine/datasources/nasa_power_weather.py
(ADR-005: NASA POWER, ne Open-Meteo — komerční licence).

STANDARDNÍ, NE VYMYŠLENÉ VZORCE. GDD je učebnicová agrometeorologie
(McMaster & Wilhelm 1997, "Growing degree-days: one equation, two
interpretations"), ne novinka. Základní teplota (base_temp) je ale
PLODINO-SPECIFICKÁ, ne univerzální konstanta — pšenice/ječmen ~0-5°C,
kukuřice/slunečnice ~10°C. Výchozí hodnota 5.0°C níže je rozumný default
pro mírně-teplotní obiloviny střední Evropy, NE fyzikální fakt platný
pro každou plodinu — volající kód (nebo budoucí UI) musí umožnit
plodino-specifickou hodnotu, jinak je to stejná chyba jako univerzální
SIGMA_DRY_REF_DB z master_plan.md (ADR-002): jedna konstanta tam, kde
realita má rozptyl podle kontextu.
"""

from datetime import datetime, timedelta


def compute_gdd(tmax: list[float], tmin: list[float], base_temp: float = 5.0) -> float:
    """
    Growing Degree Days — kumulativní tepelná suma nad prahovou teplotou.
    GDD_den = max(0, (Tmax+Tmin)/2 - base_temp), sečteno přes celé období.
    """
    if len(tmax) != len(tmin):
        raise ValueError("tmax a tmin musí mít stejnou délku")
    total = 0.0
    for hi, lo in zip(tmax, tmin):
        daily_mean = (hi + lo) / 2.0
        total += max(0.0, daily_mean - base_temp)
    return round(total, 1)


def find_last_spring_frost(dates: list[str], tmin: list[float], threshold: float = 0.0, spring_cutoff_month: int = 7) -> str | None:
    """
    Poslední jarní mráz — poslední den PŘED spring_cutoff_month, kdy Tmin < threshold.
    Vrací None, pokud v datech žádný takový den není (nebo je po cutoff — pak
    už to není "jarní" mráz, ale reálný, aktuální risk, který má řešit jiná logika).
    """
    last_frost = None
    for d, t in zip(dates, tmin):
        dt = datetime.strptime(d, "%Y-%m-%d")
        if dt.month >= spring_cutoff_month:
            continue
        if t < threshold:
            if last_frost is None or dt > datetime.strptime(last_frost, "%Y-%m-%d"):
                last_frost = d
    return last_frost


def find_first_autumn_frost(dates: list[str], tmin: list[float], threshold: float = 0.0, autumn_start_month: int = 8) -> str | None:
    """První podzimní mráz — první den OD autumn_start_month, kdy Tmin < threshold."""
    first_frost = None
    for d, t in zip(dates, tmin):
        dt = datetime.strptime(d, "%Y-%m-%d")
        if dt.month < autumn_start_month:
            continue
        if t < threshold:
            if first_frost is None or dt < datetime.strptime(first_frost, "%Y-%m-%d"):
                first_frost = d
    return first_frost


def compute_precipitation_deficit_mm(current_precip: list[float], historical_daily_mean_mm: float) -> float:
    """
    Rozdíl skutečných srážek za období vůči historickému normálu za stejně
    dlouhé období. Záporné číslo = deficit (méně pršelo než obvykle).
    historical_daily_mean_mm musí být PRŮMĚR ZA DEN (ne součet), aby šlo
    škálovat na libovolnou délku aktuálního období.
    """
    actual_total = sum(current_precip)
    expected_total = historical_daily_mean_mm * len(current_precip)
    return round(actual_total - expected_total, 1)


def historical_daily_precip_mean(dates: list[str], precip: list[float], years_exclude: set[int]) -> float:
    """Průměrné denní srážky napříč lety (mimo years_exclude, typicky aktuální rok)."""
    values = [
        p for d, p in zip(dates, precip)
        if datetime.strptime(d, "%Y-%m-%d").year not in years_exclude
    ]
    if not values:
        raise ValueError("Žádná historická data mimo vyloučené roky.")
    return sum(values) / len(values)
