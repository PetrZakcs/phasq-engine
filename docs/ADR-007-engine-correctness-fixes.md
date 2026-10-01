# ADR-007: Čtyři opravy z externí review — tři čisté, jedna odhalila hlubší problém

**Stav:** Přijato, živě ověřeno, částečně nepříjemné | **Datum:** 2026-10-01

## Kontext

Druhý agent (externí review appky i enginu) navrhl čtyři konkrétní opravy.
Všechny jsem si ověřil sám (čtením kódu, živými voláními proti CDSE), ne
převzal na slovo.

## Oprava 1: dB se počítalo před prostorovou agregací, ne po ní

Evalscript počítal `10*log10(VV)` PER PIXEL, Statistical API pak server-side
zprůměroval/percentiloval ty dB hodnoty. Matematicky stejná chyba jako #3
z master_plan.md (průměr v dB škále), jen prostorově přes pixely v jedné
scéně místo časově přes scény.

**Živě ověřeno:** stejná scéna, dvě cesty — server zprůměroval dB hodnoty
přímo: **-10,856 dB**. Server zprůměroval lineární hodnoty, pak převod na
dB: **-10,233 dB**. Rozdíl **0,624 dB** — ~10 % šířky naší referenční
škály. Ne kosmetika.

**Oprava:** evalscript vrací lineární hodnoty (`_backscatter_linear_evalscript`),
dB převod až v Pythonu po agregaci (`linear_to_db` ze sdíleného
`utils/decibel.py`). Percentily komutují s monotónní transformací (dB
převod po přijetí je matematicky stejný jako před), mean ne — proto musel
server agregovat lineárně.

## Oprava 2: `valid_pixel_ratio` počítal špatný poměr

Podle dokumentace Sentinel Hub: `sampleCount` = pixely v **bounding boxu**
geometrie, ne v polygonu. `noDataCount` = pixely MIMO polygon i skutečně
chybějící data, nerozlišeně. `geometryPixelCount` (top-level pole v
odpovědi) = `sampleCount - noDataCount`, živě ověřeno přesně (3752 = 3752).

Živě ověřeno navíc: `geometryPixelCount` je konstantní napříč scénami pro
stejné AOI (čistě geometrický údaj), zatímco `sampleCount`/`noDataCount`
byly identické pro všech 6 testovaných dní — pro tohle pole žádný den
neměl ztrátu dat NAD RÁMEC geometrie.

**Oprava:** `valid_pixel_ratio = (sampleCount - noDataCount) / geometryPixelCount`,
ne původní `sampleCount / (sampleCount + noDataCount)`, ani agentem
navržené `(sampleCount - noDataCount) / sampleCount` (to by pro
nepravidelné pole měřilo hlavně tvar pole vůči obdélníkovému obalu, ne
kvalitu dat — `geometryPixelCount` tenhle zkreslující efekt odstraňuje).

## Oprava 3: NDVI hradlo nebylo zapojené v živém API

`HistoricalBaselineCalculator(source)` se v `api/routes/analysis.py`
volalo BEZ `ndvi_source` — hradlo bylo postavené, otestované, v ADR-002
označené "hotovo, funguje", ale nikdy se skutečně nepoužívalo mimo
izolované testy. Nalezeno externí review, ne vlastním testem.

**Oprava:** `Sentinel2NDVISource` se teď vytváří a předává v
`analyze_radiometric()`.

### Co tahle oprava odhalila — nepříjemné, ale důležité

Živý test na stejném poli (Havlíčkobrodsko, k 9. 9. 2026) se VŠEMI
čtyřmi opravami najednou: `reference_source = global_fallback`,
`relative_moisture_pct = 89 %`, `drought_severity = none`.

Důvod (ověřeno): NDVI hradlo vyřadilo 35 scén kvůli "husté vegetaci" —
ozimá pšenice v tomhle regionu běžně má NDVI nad 0,35 i ve vodním
stresu (přesně ten jev, co ADR-002 už zdokumentovalo jako
"NDVI hradlo padlo pod vlastní kontrolou"). Zbyly jen 2 kvalifikované
roky z 5, pod hranicí `MIN_YEARS_FOR_MEDIAN=3` — systém správně spadl
na globální fallback.

**Co to znamená:** náš dosavadní "nejlepší" výsledek z ADR-003/ADR-006
(56,4 %, `local_baseline`, "mírné sucho" — blíž k Intersucho realitě než
globální konstanty) vznikl TÍM, že NDVI hradlo nikdy neběželo. Jakmile
běží (jak bylo od začátku zamýšleno a zdokumentováno), lokální baseline
pro tohle pole k tomuto datu **vůbec nejde spočítat** — systém se
správně chová fail-safe, ale výsledné číslo (89 %, globální fallback)
je DÁL od Intersucho reality než náš dřívější, částečně vadný výsledek.

**Důsledek:** nikdy jsme neměli jeden plně funkční, od začátku do konce
správně zapojený běh celé zamýšlené metodiky na tomhle poli, co by dal
uspokojivý výsledek. Threshold `DENSE_VEGETATION_NDVI_THRESHOLD=0.35` —
už dřív zdokumentovaný jako "nekalibrovaný na víc než dvě pole" v
ADR-002 — je teď AKTIVNĚ blokující problém na našem vlajkovém
validačním poli, ne teoretická poznámka pod čarou.

## Oprava 4: `pytest-asyncio==0.23.0` → `0.23.8`

Shoduje se s problémem, na který jsme sami narazili dřív (`'Package'
object has no attribute 'obj'`) — tehdy jsme to obešli odstraněním
`tests/__init__.py`, ne opravou verze. `0.23.8` řeší kořen, ne jen
příznak u nás. 37/37 testů zelených po upgradu.

## Co dál

Priorita se mění: **kalibrace NDVI prahu** (nebo nahrazení jiným
mechanismem rozlišení vegetace/vlhkosti) teď blokuje, ne jen omezuje,
naši schopnost ukázat funkční `local_baseline` na reálném poli. Dokud
se to nevyřeší, každá demo-schopná analýza bude pravděpodobně na
`global_fallback` — což je bezpečné (žádné falešné sebevědomí), ale ne
to, co jsme si mysleli, že máme hotové.
