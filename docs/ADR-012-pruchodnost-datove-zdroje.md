# ADR-012: Datové zdroje pro průjezdnost terénu (Fáze 1)

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-10-13

Zadání žádalo `ADR-011-pruchodnost-datove-zdroje.md` - číslo už bylo
obsazené Fází 0 (viz `ADR-011-ndvi-threshold-parametrizace.md`, kolize
zdůvodněná tam). Tohle je `ADR-012`, následující (klasifikace, validační
kritéria) jsou `ADR-013`/`ADR-014`.

## Shrnutí

| Zdroj | Dostupnost (živě ověřeno) | Licence | Rozlišení | Latence/aktuálnost |
|---|---|---|---|---|
| Copernicus DEM GLO-30 | AWS Open Data S3 (`copernicus-dem-30m`), bez autentizace | Free, komerčně OK, nutná atribuce (plný text licence přečten) | 30 m | Statická (jedna verze, bez průběžných aktualizací) |
| SoilGrids (ISRIC) | WCS (`maps.isric.org`), REST API je mrtvé | CC BY 4.0 | 250 m | Statická (2020 verze) |
| ESA WorldCover | AWS S3 (`esa-worldcover`), bez autentizace | CC BY 4.0 | 10 m | Statická (2021 verze, `v200`) |
| ERA5-Land (CDS) | Vyžaduje SAMOSTATNÝ ECMWF/CDS účet, ne CDSE | CC-BY (komerčně OK) | ~9 km | Finální produkt 2-3 měsíce staré; NRT varianta (ERA5-Land-T) ~5 dní, ale nekvalitně ověřená data |
| NASA POWER srážky (existující) | Už integrováno | Volně pro cokoliv (ADR-006) | bod | **Živě ověřeno teď: 4 dny** (lepší než GWETROOT ~9-10 dní) |

**Závěr: tři ze čtyř nových zdrojů (DEM, SoilGrids, WorldCover) jsou
čisté a přímo použitelné. ERA5-Land má stejný problém jako EGMS v
`engine/ki` (ADR-009) - samostatný credential, navíc s latencí, co
dělá "objemovou vlhkost 0-7cm" prakticky nepoužitelnou pro "aktuální
stav terénu".**

## Detailní nálezy

### Copernicus DEM GLO-30 - CDSE Sentinel Hub ho NEOBSLUHUJE zdarma

Živě ověřeno: dotaz na `sh.dataspace.copernicus.eu/api/v1/statistics`
s `"type": "dem", "demInstance": "COPERNICUS_30"` (stejný vzor jako
Sentinel-1/2) vrací `403 COMMON_INSUFFICIENT_PERMISSIONS` s existujícími
CDSE credentials. Sentinel Hub dokumentace, co DEM popisuje, je pro
komerční `services.sentinel-hub.com`, ne pro CDSE free instanci - matoucí,
protože návod vypadá stejně.

**Funkční cesta:** AWS Open Data, bucket `copernicus-dem-30m`,
bez jakékoliv autentizace. Živě ověřeno - dlaždice
`Copernicus_DSM_COG_10_N49_00_E015_00_DEM.tif` (pokrývá testovací pole
u Havlíčkova Brodu) stažena, 200 OK, Cloud-Optimized GeoTIFF (podporuje
HTTP range requesty, nemusí se stahovat celá dlaždice).

**Licence (plný text přečten, `License-COPDEM-30.pdf`):** volná pro
"General Public", práva zahrnují reprodukci, distribuci a explicitně
"adaptation, modification and combination with other data" (čl. 4) -
pokrývá výpočet sklonu z dat. Povinná atribuce při distribuci/úpravě:
"produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and ©
Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
the European Union and ESA; all rights reserved". Žádná komerční
výjimka ani omezení v textu.

**Implementační poznámka pro Fázi 2:** sklon se musí dopočítat sám
(finite-difference gradient na staženém gridu přes `rasterio`, už
pinovaná závislost) - žádný zdroj výše neposkytuje sklon přímo.

### SoilGrids - REST API je mrtvé, WCS funguje

Živě ověřeno: `docs.isric.org` sám přiznává, že REST API je "dočasně
pozastavené" (`"we have decided to temporarily pause the service"`),
bez odhadu obnovy. WCS (`maps.isric.org/mapserv?map=/map/clay.map`)
funguje živě - `GetCapabilities` i skutečný `GetCoverage` dotaz (40×40px
TIFF) otestovány, sand/silt mají stejný vzor (`/map/sand.map`,
`/map/silt.map`). Licence CC BY 4.0 od 2019 (starší zmínky o ODbL se
týkají V1, dnes neplatí).

### ESA WorldCover - AWS S3, žádná autentizace

Živě ověřeno: `esa-worldcover.s3.eu-central-1.amazonaws.com`, dlaždice
pojmenované `ESA_WorldCover_10m_2021_v200_N48E015_Map.tif` (schéma
podle severozápadního rohu 3°×3° dlaždice). CC BY 4.0. **Poznámka:**
poslední verze je 2021 (`v200`) - k 2026 je to 5 let stará statická
vrstva. Pro třídu pokryvu (orná půda/louka/les/voda/zástavba) by změna
za 5 let měla být vzácná, ale není to živá vrstva - zadání rule 1
("Pokryv mimo ornou půdu nebo louku → Nelze určit") se opírá o data, co
mohou být zastaralá u nedávno změněného využití půdy (nová zástavba,
odlesnění). Patří do `caveat` pole výstupu.

### ERA5-Land (CDS) - samostatný účet, latence dělá "0-7cm objemovou vlhkost" téměř nepoužitelnou

Živě ověřeno (WebSearch + oficiální ECMWF Confluence dokumentace):
CDS (`cds.climate.copernicus.eu`) je JINÁ platforma než CDSE - sdílí
nově (2026) jednotné ECMWF přihlášení napříč CDS/ADS/EWDS/ECDS, ale
pořád je to samostatná registrace, ne CDSE credentials, co appka už má.

Dva produkty, zásadně jiná latence:
- **ERA5-Land (finální):** kvalitně ověřená data, ale 2-3 MĚSÍCE stará.
  Pro "aktuální stav terénu" k ničemu.
- **ERA5-Land-T (NRT):** ~5 dní staré, ale NEkvalitně ověřená atmosférická
  forcing data (ne finální korekce) - a jeden hlášený případ na fóru
  ECMWF (2025) uvádí reálnou latenci horší než deklarovaných 5 dní,
  neoficiálně nepotvrzeno.

**Důsledek pro klasifikaci (Fáze 2):** objemová vlhkost 0-7cm z
ERA5-Land nebude k dispozici aktuální ani v nejlepším případě - buď
"Nelze určit" dokud nebude `CDS_API_KEY` k dispozici (stejný vzor jako
`engine/ki/datasources/egms.py`), nebo (pokud se token získá) vždy
s jasně označenou minimální stářím ~5 dní, nikdy jako "dnešní stav".

### Vedlejší nález: NASA POWER srážky mají 4denní latenci (živě ověřeno teď)

`nasa_power_weather.py` dosud latenci srážek (`PRECTOTCORR`) nikde
netrackoval (na rozdíl od `nasa_power_rootzone.py`, co ji trackuje pro
GWETROOT přesně, viz ADR-006). Živý dotaz na posledních 15 dní k
2026-10-13 ukazuje poslední NEvyplněnou (ne `-999.0` fill value) hodnotu
pro **2026-10-09** - tedy **4denní latence**, lepší než GWETROOT (~9-10
dní), ale pořád relevantní: zadání (pravidlo 3/4 klasifikace) počítá se
"srážky za posledních 72 hodin", což při 4denní latenci znamená, že
NEJNOVĚJŠÍ dostupné 72h okno je samo o sobě už ~4-7 dní staré, ne
opravdu "posledních 72 hodin" v reálném čase. Patří do `caveat` pole u
srážkového pravidla, ne něco, co jde opravit kódem.

## Co zůstává pro Fázi 2 (implementace)

- `engine/trafficability/datasources/dem.py` - AWS S3 COG stahování +
  `rasterio` finite-difference sklon
- `soilgrids.py` - WCS klient (jiný vzor než ArcGIS REST z `engine/ki`)
- `worldcover.py` - AWS S3 COG, point-sample na jeden pixel (land cover
  třída pod objektem)
- `era5_cds.py` - stub jako `engine/ki/datasources/egms.py`, honest
  "Nelze určit" bez `CDS_API_KEY`
- Threading `dense_vegetation_ndvi_threshold=0.5` (ADR-011) do volání
  `HistoricalBaselineCalculator` v `engine/trafficability/run.py`
