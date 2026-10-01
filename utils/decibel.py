"""
Sdílené dB/lineární konverze — engine/physics/radiometric.py (časová
agregace přes scény) i engine/datasources/sentinel1_cdse.py (prostorová
agregace přes pixely, oprava 2026-10-01). Jedno místo pravdy, ne dvě
kopie téhož vzorce, co by se mohly rozejít.
"""

import math


def db_to_linear(db: float) -> float:
    return 10 ** (db / 10.0)


def linear_to_db(linear: float) -> float:
    if linear <= 0:
        return -50.0
    return 10 * math.log10(linear)


def approx_stddev_db(stddev_linear: float, mean_linear: float) -> float:
    """
    PŘIBLIŽNÝ převod směrodatné odchylky z lineární škály do dB (delta
    metoda / error propagation přes derivaci 10*log10(x)). Na rozdíl od
    mean/percentilů (které přes monotónní transformaci PŘESNĚ komutují)
    směrodatná odchylka ne — tohle je aproximace platná pro menší rozptyl,
    ne exaktní vzorec. Použito jen informativně, nikde v drought/moisture
    výpočtu se stddev_db nepoužívá jako vstup.
    """
    if mean_linear <= 0:
        return 0.0
    return stddev_linear * (10.0 / (mean_linear * math.log(10)))
