# ADR-010: Fáze 1 - mapový podklad přírodních rizik, jeden objekt

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-10-08

## Kontext

Navazuje na ADR-009 (ověření datových zdrojů). Cíl Fáze 1 dle zadání:
pro jeden veřejně známý objekt vygenerovat PDF + GeoPackage + JSON s
výsledky pro povodně (Q5/Q20/Q100), sesuvy, poddolování a EGMS, každá
hodnota se zdrojem.

## Architektura

Nový modul `engine/ki/`:
- `models.py` - `KiObject`, `ThreatFinding`, `ObjectReport`
- `scale.py` - převod na stupnici tabulky č. 1 (čistá logika, bez I/O,
  plně testováno včetně hraničního případu Q20)
- `datasources/arcgis_rest.py` - sdílený ArcGIS REST query klient (VÚV i
  ČGS používají stejné rozhraní)
- `datasources/flood_zones.py`, `landslides.py`, `undermining.py` - živě
  napojené na zdroje z ADR-009
- `datasources/egms.py` - záměrně nedokončený stub, viz níže
- `report.py` (PDF), `geopackage.py`, `json_output.py` - výstupy
- `run.py` - CLI, `python -m engine.ki.run --input X --out Y`

Zdroje si navzájem nic nepředávají ani se neovlivňují - každý vrací
`(ThreatFinding, raw_features)` nezávisle, `run.py` je jen orchestruje.

## Rozhodnutí a nálezy

### EGMS vyžaduje samostatný CLMS token, ne CDSE

Živě ověřeno (WebFetch na egms.land.copernicus.eu + github.com/
copernicus-land/egms-api README): EGMS distribuce vyžaduje registraci
na land.copernicus.eu a vlastní API token (`CLMS_API_TOKEN`), CDSE
credentials (co appka už má pro Sentinel-1) nestačí. Modul
`datasources/egms.py` je proto záměrně stub - vrací čestné "Nelze
určit" s vysvětlením, ne smyšlenou hodnotu (zadání pravidlo 1). Skutečné
stažení je otevřený bod, až bude token k dispozici.

### Žádné datum poslední aktualizace z ArcGIS REST API

Živě ověřeno u všech tří funkčních zdrojů (VÚV, ČGS×2): odpověď
neobsahuje `editingInfo`/datum editace. Report proto u `source_date`
píše "neuvedeno v API zdroje" místo smyšleného data - jediná výjimka je
pole `rok` u poddolovaných území, které ČGS u některých záznamů uvádí.

### Geometrie - jen bod, ne polygon

Zadání sice počítá s "body nebo polygony", ale pro Fázi 1 (i reálně pro
`engine/ki/run.py`) používám jen bod - objekt (úpravna vody, elektrárna
apod.) je dost malý, že střed/reprezentativní bod stačí pro point-in-
polygon test proti záplavovým zónám i pro vzdálenostní dotazy. Podpora
polygonů (přesnější pro rozsáhlé areály) je otevřený bod pro další fázi,
ne něco, co bylo zapomenuto.

### Demo objekt: Úpravna vody Želivka

Poloha NENÍ odhadnuta podle obce (to by pro point-in-polygon test proti
úzkým záplavovým zónám mohlo dát falešný výsledek) - dohledána přesně
přes OpenStreetMap Nominatim jako zdokumentovaný areál (way 249680930,
landuse=industrial, name="Úpravna vody Želivka"), s uvedeným zdrojem v
`source_note`. Provozovatel (Želivská provozní, s.r.o.) ověřen
nezávisle webovým vyhledáváním. Splňuje zadání pravidlo 4 (veřejně
známá poloha).

### Fonty - DejaVu Sans, bundlováno v repu

Reportlab defaultní Helvetica NEMÁ českou diakritiku (živě zjištěno při
prvním běhu - ř/ě/č/š/ž/ů se vykreslily jako černé čtverečky, PDF bylo
fakticky nepoužitelné). `engine/ki/fonts/DejaVuSans.ttf` +
`DejaVuSans-Bold.ttf` staženo z oficiálního GitHub release (dejavu-fonts
2.37), ověřeno skriptem přes fontTools, že pokrývá všechny české
diakritické znaky. Licence (Bitstream Vera License, `engine/ki/fonts/
LICENSE`) volně pro jakékoliv použití včetně komerčního a redistribuce.

### Závislosti: numpy/shapely/pyproj zvednuty kvůli geopandas

GeoPackage výstup potřebuje `geopandas` (+ `pyogrio` pro I/O), což
vyžadovalo zvednout `numpy`, `shapely`, `pyproj` nad verze, co měl
projekt napevno přišpendlené. Ověřeno: všech 42 dřívějších testů
prochází beze změny + živý sanity check `utils/reproject.py` (stejný
EPSG, stejné souřadnice jako před bumpem).

## Výstup Fáze 1 (živě vygenerováno)

`engine/ki/examples/objekty_zelivka.geojson` → PDF (2 strany), GeoPackage
(4 vrstvy: `objekty`, `vysledky`, `podklad_svahove_nestability`,
`podklad_poddolovani` - `podklad_zaplavova_uzemi` chybí, protože objekt
leží mimo všechny tři zóny, žádné prvky k uložení), JSON.

Výsledek pro Želivku: mimo Q5/Q20/Q100 (úroveň 1, Zanedbatelná), nejbližší
sesuv 2397 m, nejbližší poddolování 557 m, EGMS nelze určit.

## Testy

62/62 testů zelených (42 původních + 20 nových: 7 `test_scale.py`,
13 napříč třemi datasource moduly + EGMS stub).

## Co zůstává pro další fázi

- EGMS skutečné stažení (čeká na `CLMS_API_TOKEN`)
- Fáze 2 (dávka 20 objektů) a Fáze 3 (pozorované povodně ze Sentinelu-1)
  dle zadání, nezačato
- Podpora polygonové (ne jen bodové) geometrie objektu
