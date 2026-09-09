# ADR-005: Audit datových zdrojů na komerční licenci, NASA POWER místo Open-Meteo

**Stav:** Přijato, částečně otevřené | **Datum:** 2026-09-09

## Kontext

Před nabídkou softwaru komerčně bylo potřeba ověřit, jestli všechny
datové zdroje dovolují komerční použití zdarma — ne předpokládat.

## Audit (živě ověřeno, se zdroji)

| Zdroj | Komerční použití zdarma? | Zdroj ověření |
|---|---|---|
| CDSE (Sentinel-1/2) | ✅ Ano | copernicus.eu/en/access-data/copyright-and-licences |
| ERA5-Land přes **Open-Meteo** | ❌ **Ne** — vyžaduje placený tarif | open-meteo.com/en/terms |
| ERA5-Land přímo přes **CDS** | ✅ Ano (jen atribuce, CC-BY od 7/2025) | cds.climate.copernicus.eu/licences/licence-to-use-copernicus-products |
| **NASA POWER** | ✅ Ano, bez atribuce (public domain) | power.larc.nasa.gov (NASA open data policy) |
| Esri World_Imagery dlaždice | ❌ **Ne** — explicitně zakázáno bez ArcGIS licence | Esri Community Terms of Use |
| Mapbox (`mapbox-gl`) | mrtvá závislost, nikde v kódu nepoužitá | vlastní grep, 0 výskytů |
| CENIA LPIS WFS | ❓ nezjištěno — řeší se přímo s MZe | — |

## Rozhodnutí: agroklimatika (Fáze B) → NASA POWER, ne Open-Meteo ani CDS

`engine/datasources/era5_weather.py` přepsán z Open-Meteo na NASA POWER
(`power.larc.nasa.gov`) — zdarma pro jakékoliv použití, bez registrace,
bez API klíče, synchronní REST API (žádná změna architektury).

**Živě ověřeno:** NASA POWER MÁ i kořenovou zónu (`GWETROOT`/`GWETPROF`/
`GWETTOP`) — ale s reálným zpožděním ~9-10 dní (MERRA-2 reanalýza).
K datu 2026-09-09 měla poslední platná data k 2026-08-30.

**Proto rozdělené rozhodnutí, ne jedno řešení pro vše:**
- **Agroklimatika (GDD, mráz, srážkový deficit)** — latence nevadí,
  počítáme sezónní součty. NASA POWER: nejjednodušší, nejlevnější (0 Kč),
  nejméně tření (žádná registrace). Přepnuto.
- **Živá kořenová zóna (ADR-003, `era5_land.py`)** — latence VADÍ, právě
  tahle funkce dala náš nejsilnější důkaz ("dnešní hodnota pod 5letým
  minimem"), NASA POWER by k dnešnímu dni neměla vůbec data. Zůstává na
  Open-Meteo (NENÍ zdarma komerčně) — **otevřený problém, neuzavřeno**.
  Cesta k uzavření: přímé CDS API s near-real-time (ERA5T) datovým
  proudem — vyžaduje registraci a živé ověření skutečné latence dřív,
  než se do toho investuje inženýrská práce (async job queue místo
  synchronního volání).

Živě přepočteno na reálném poli: GDD 1736,6 (dřív 1763,0 přes ERA5),
srážkový deficit -144,6 mm (dřív -134,2 mm) — jiná reanalýza (MERRA-2 vs.
ERA5), řádově stejný výsledek. Nezávislé potvrzení navíc, ne jen náhrada.

## Co zůstává otevřené

1. **Živá kořenová zóna pořád na Open-Meteo** — komerčně nevyřešeno.
2. **Esri mapové dlaždice** — samostatný problém, řeší se odděleně.
3. **CENIA LPIS WFS licence** — nezjištěno, řeší se přímo s MZe.
