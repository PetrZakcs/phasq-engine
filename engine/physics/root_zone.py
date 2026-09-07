"""
Kořenová zóna přes exponenciální SWI filtr (Wagner et al. 1999).

PROČ TOHLE EXISTUJE (viz ADR-002, "co je otevřené"):
Sentinel-1 VV backscatter měří jen svrchních ~0-5 cm půdy. Živá validace
2026-08-30 ukázala, že to je skutečný, ne kosmetický rozdíl proti tomu, co
hlásí Intersucho.cz (profil 0-100 cm z pozemních stanic). Tenhle modul
NEŘEŠÍ to přeměřením hlouběji — SAR hlouběji nevidí, žádná fyzika to
nezmění. Řeší jen ČASOVOU extrapolaci: opakovaná pozorování povrchové
vlhkosti v čase nesou informaci o tom, jak se vlhkost postupně
"propisuje" do hlubší vrstvy, přes charakteristickou časovou konstantu T.

METODA: Soil Water Index (SWI) — standardní rekurzivní exponenciální filtr
z Wagner et al. (1999), "A Method for Estimating Soil Moisture from ERS
Scatterometer and Soil Data", používaný provozně v ESA/EUMETSAT H-SAF
produktech. Ne nová metoda, jen dosud nezapojená.

    SWI(t_k) = SWI(t_{k-1}) + K_k · (SSM(t_k) − SWI(t_{k-1}))
    K_k = K_{k-1} / (K_{k-1} + exp(−Δt / T))
    K_1 = 1  (první pozorování se bere jak je)

T (dny) určuje, jak "hluboko" filtr efektivně integruje — malé T (dny) ~
mělká vrstva, velké T (týdny až měsíce) ~ hlubší kořenová zóna. Literatura
běžně používá T≈20 dní jako obecnou hodnotu pro mělce kořenující plodiny
(H-SAF SWI produkt nabízí T ∈ {1,5,10,15,20,40,60,100} dní).

POCTIVĚ: T=20 dní níže je DEFAULT Z LITERATURY, NE LOKÁLNĚ KALIBROVANÁ
HODNOTA pro české půdy/plodiny. Máme reálnou cestu, jak to zkalibrovat:
Intersucho.cz sám rozlišuje stanice v hloubce 0-40 cm a 50-100 cm — to je
přesně ground truth, proti kterému by šlo T fitovat (minimalizovat chybu
SWI(T) vs. hlubinné stanice). Tohle NENÍ dnes uděláno — je to konkrétní,
ne abstraktní příští krok.

DRUHÉ POCTIVÉ OMEZENÍ (zjištěno při zapojování, ne po faktu): tak, jak je
tenhle filtr zapojen do RadiometricAnalyzer.analyze(), počítá se ZNOVA od
K=1 při KAŽDÉM volání, nad scénami jen z aktuálního analytického okna
(typicky ~6 scén za 2 týdny). To vyhlazuje šum UVNITŘ jednoho okna, ale
NEŘEŠÍ šum MEZI samostatnými snímky v čase (ADR-002 "poslední otevřená
vrstva": skok 19,3 % -> 61,5 % za 15 dní mezi měsíčními snímky s vlastní
nově spočítanou referencí). Skutečná oprava tamtoho problému potřebuje
SWI stav přenášený napříč voláními (kontinuální filtr nad měsíce/roky
dlouhou řadou), ne per-request reset. To je odlišný, zatím neudělaný krok.
"""

from datetime import datetime

import numpy as np


def compute_swi(dates: list[str], ssm_values: list[float], t_days: float = 20.0) -> list[float]:
    """
    Vstup: časová řada povrchové vlhkosti (%), SEŘAZENÁ vzestupně podle data.
    Výstup: stejně dlouhá řada SWI hodnot (%) — vyhlazená, časově integrovaná verze.

    Chybí-li >1 vstup, vrací vstup beze změny (není co filtrovat).
    """
    if len(dates) != len(ssm_values):
        raise ValueError("dates a ssm_values musí mít stejnou délku")
    if len(ssm_values) <= 1:
        return list(ssm_values)

    parsed = [datetime.strptime(d, "%Y-%m-%d") for d in dates]

    swi = [ssm_values[0]]
    k_prev = 1.0
    for i in range(1, len(ssm_values)):
        delta_t = max((parsed[i] - parsed[i - 1]).days, 1)
        k = k_prev / (k_prev + np.exp(-delta_t / t_days))
        swi_i = swi[-1] + k * (ssm_values[i] - swi[-1])
        swi.append(float(swi_i))
        k_prev = k

    return swi
