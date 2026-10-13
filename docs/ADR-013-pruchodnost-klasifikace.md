# ADR-013: Klasifikační logika průjezdnosti terénu (Fáze 2)

**Stav:** Přijato, živě ověřeno na reálném poli | **Datum:** 2026-10-13

Zadání žádalo `ADR-012` pro klasifikaci - obsazeno datovými zdroji (viz
číslovací kolize zdůvodněná v ADR-011/ADR-012). Tohle je `ADR-013`,
validační kritéria (zadání `ADR-013`) budou `ADR-014`.

## Kontext

Zadání kap. 4 dává "navrženou strukturu" šesti pravidel s instrukcí
"uprav podle literatury a zdůvodni v ADR" a nevyjednatelným pravidlem:
"Žádný vymyšlený práh. Pokud práh nejde doložit, pravidlo nepoužívej a
zapiš to do ADR." Tahle ADR dokumentuje, co z navržené struktury přežilo
beze změny, co se upravilo, a co se ZCELA VYPUSTILO, protože se pro to
nenašel doložitelný obecný práh.

## Implementace: `engine/trafficability/classify.py` (čistá logika, bez I/O)

### Pravidlo 1 (beze změny): pokryv mimo ornou půdu/louku -> Nelze určit

ESA WorldCover v200: 40=Cropland, 30=Grassland v rozsahu, vše ostatní
mimo (živě ověřeno proti legendě, ADR-012).

### Pravidlo 2 (beze změny): `reference_source != local_baseline` -> Nelze určit

Přímo navazuje na ADR-008 (global_fallback nesmí dávat verdikt) -
stejný princip, jiná doména.

### Pravidla 3-5: relativní vlhkost + srážky za 72h

**`RELATIVE_MOISTURE_HIGH_PCT = 90.0`** - literatura konverguje k 90-95 %
field capacity jako kritériu "nesjízdno" (historická Ontario/Guelph
kritéria 90-95 % FC; kalifornská HYDRUS-1D studie 85-95 % FC podle
textury - 85 % pro jíly/jílovité hlíny, 95 % pro písky). `relative_moisture_pct`
NENÍ doslova % field capacity (je to pozice mezi lokálním SAR 5./95.
percentilem) - použito jako ROZUMNÁ ANALOGIE, explicitně zdokumentovaná
jako taková, ne jako fyzikálně identická veličina. Zvolen konzervativnější
(vyšší) konec citovaného rozsahu.

**`PRECIP_72H_RISK_MM = 5.0`** - NÍZKÁ DŮVĚRYHODNOST, přiznaná v kódu i
testech. Jediná nalezená studie s konkrétní mm hodnotou je brazilská
(denní srážky <5mm = příznivý den), jiný klimatický region, denní ne
kumulativní hodnota. Teagasc (irská extenze) podporuje časové okno
("bezpečno 1-2 dny po dešti"), ale bez vlastního mm čísla. Použito s
otevřeně přiznanou nejistotou, ne s falešnou jistotou.

**Živě naměřený vedlejší efekt (ADR-012):** NASA POWER srážky mají
~4denní latenci - "posledních 72h" v `classify.py` je ve skutečnosti
nejnovější DOSTUPNÉ 72h okno, obvykle staré ~4-7 dní. `precip_data_age_days`
se promítá do `confidence`, ne do samotného prahu - při živém testu na
reálném poli (Havlíčkobrodsko, 2026-10-13) tohle snížilo spolehlivost na
"střední" a jasně to uvedlo v `caveat`.

### Pravidlo 6: textura ANO, sklon NE

**`CLAY_HIGH_PCT = 40.0`** - hranice USDA půdní texturní třídy "Clay"
(Soil Survey Manual), standardní taxonomická klasifikace, ne empiricky
odvozený práh průjezdnosti specificky. Literatura o průjezdnosti dává
jíl jako kvalitativní rizikový faktor (vertisoly, jílovité horizonty)
bez vlastního číselného prahu - proto nejbližší OBJEKTIVNÍ doložitelná
hranice.

**Sklon: VYPUŠTĚN z klasifikační logiky.** Hledání (NATO NRMM/AVT-308,
agrotechnická literatura, FAO/USDA land capability klasifikace) nenašlo
obecný, na konkrétním stroji nezávislý práh. Jediné nalezené konkrétní
hodnoty byly specifikace jednotlivých kombajnů (10-38 % podle výrobce/
modelu) - nepřenositelné na "obecnou třídu těžké zemědělské techniky"
(zadání kap. 2). Sklon se počítá (`engine/trafficability/datasources/dem.py`,
Horn's method finite-difference gradient na Copernicus DEM GLO-30) a
reportuje jako informativní `LayerReading`, ale NEOVLIVŇUJE klasifikaci.
Tohle je odchylka od navržené struktury v zadání - úmyslná, zdokumentovaná,
ne přehlédnutá.

### Spolehlivost (`confidence`)

Odvozena z: skoková změna backscatteru (nízká), stáří Sentinel-1 scény
>6 dní (střední), stáří srážkových dat >3 dny (střední), chybějící
textura (střední), jinak vysoká. **Živě ověřeno**, že reálný běh s
NASA POWER srážkami (vždy ~4denní latence) typicky NEDOSÁHNE "vysoká" -
to je správné chování, ne bug (viz `test_realistic_precip_latency_caps_confidence_at_medium`).

### Detekce skokové změny (STATUS #10, zadání kap. 7.2)

"V1: detekuj skokovou změnu backscatteru a označ ji jako sníženou
spolehlivost, neopravuj." Implementováno jako: změna mezi posledními
dvěma scénami > 50 % lokálního dry-wet rozpětí (z `local_reference`,
ne globální konstanta - stejný princip "lokální, ne globální" jako
ADR-002). Tohle NENÍ literaturní fyzikální práh (proto bez citace) - je
to heuristika datové kvality odvozená z POLE VLASTNÍ kalibrace.

## Živý test na reálném poli

`engine/trafficability/examples/pole_havlickobrodsko.geojson` (stejná
LPIS parcela jako `tests/fixtures/real_lpis_arable_field.json`,
k 2026-10-13): `local_baseline` úspěšně spočítána (threshold=0.5 z
ADR-011 funguje i tady), `relative_moisture_pct=0,0 %` (pole aktuálně
suché dle posledního Sentinel-1 snímku z 2026-10-11), ale srážky 6,4 mm
v nejnovějším dostupném (ale 4 dny starém) okně -> **Riziko** přes
Pravidlo 4. Sklon 6,8 %, jíl 17,3 % (pod prahem, nezvyšuje třídu).

Tohle je přesně ten typ napětí, co měl systém zachytit, ne skrýt: aktuální
povrchová vlhkost je nízká, ale nedávný (byť opožděně reportovaný) déšť
zvyšuje riziko - výstup obojí jasně ukazuje, nenutí to do jednoho
zavádějícího čísla.

## Testy

`tests/trafficability/test_classify.py`: 23 testů včetně hraničních
případů (hodnota přesně na prahu vs. těsně pod, pravidlo 6 nesmí
přetéct přes "Nevhodné", sklon záměrně není ani polem vstupu).

88/88 testů zelených (65 z předchozích fází + 23 nových).

## Co zůstává pro Fázi 3

Validace V-A/V-B podle ADR-014 - žádné z číslo v týhle ADR není zatím
nezávisle ověřené proti realitě, jen proti literatuře a vnitřní
konzistenci.
