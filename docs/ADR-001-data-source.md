# ADR-001: Datový zdroj = Copernicus Data Space Ecosystem, ne Google Earth Engine

**Stav:** Přijato | **Datum:** 2026-08-30

## Kontext

`phasq_cto_master_plan.md` (sekce 1.2, 5.1) definuje `DataSource` abstrakci a zároveň
prohlašuje sovereignty-first architekturu jako podmínku pro budoucí evropské vládní
zákazníky ("data nesmí opustit EU infrastrukturu", "vendor nesmí mít přístup k
zákaznickým datům"). Referenční pseudokód v sekci 1.2 ale implementuje
`Sentinel1GEESource` proti Google Earth Engine.

GEE je Google Cloud služba. To je přímý konflikt s vlastním pozicováním dokumentu —
ne detail k doladění v pozdější fázi.

## Rozhodnutí

Primární (a jediný pro Fázi 1) `DataSource` je **Copernicus Data Space Ecosystem
(CDSE)** — oficiální ESA/EU nástupce Copernicus Open Access Hub, hostováno na
OVHcloud (Francie).

Konkrétně používáme **Sentinel Hub Statistical API** (součást CDSE) pro Fázi 1:
- server-side zonální statistiky (mean, percentily, stddev) nad AOI a časovým oknem
- žádný Google, žádný vendor lock-in na úrovni cloudu

**Oprava k předchozí verzi tohoto ADR:** původně jsem tvrdil, že evalscript umí
aplikovat skutečný okolní-pixel speckle filtr (Refined Lee) před redukcí na
statistiky. To jsem si nemohl ověřit (žádný přístup k aktuální Sentinel Hub
dokumentaci v okamžiku psaní) a `evaluatePixel` v evalscriptu v3 běží
primárně per-pixel bez garantovaného přístupu k sousedním pixelům. Netvrdím to
dál jako fakt. Pro Fázi 1 řešíme šum jinak (viz níže) a skutečný Refined Lee
kernel je otevřená položka — ověřit proti live Sentinel Hub docs, případně
řešit přes windowed raster pull (rasterio/scipy) až u plných-pole modulů
(fáze 2), ne tvrdit, že to evalscript vyřeší zadarmo.

Plné pixelové matice (SLC produkty, PolSAR, InSAR) půjdou přes CDSE S3
(`eodata` bucket) až ve Fázi 2, kdy jsou skutečně potřeba.

## Důsledek pro `SAR_Scene` kontrakt

Master plan definuje `SAR_Scene.backscatter_db: np.ndarray` jako povinné pole
(plná 2D matice). To předpokládá, že DataSource vždy stahuje pixely a fyzika je
počítá v numpy. Pro Fázi 1 to nepotřebujeme a zbytečně by to řešilo problém
(GEE `getInfo()`/`computePixels()` limity), který u CDSE Statistical API vůbec
nevzniká, protože redukci dělá server.

Odchylka od doslovného pseudokódu master planu:

```python
@dataclass
class SAR_Scene:
    ...
    roi_stats: dict            # {"mean_db", "p10_db", "p90_db", "stddev_db"} — PRIMÁRNÍ pole Fáze 1
    backscatter_db: np.ndarray | None = None   # plná matice — jen když si ji DataSource vyžádá explicitně (Fáze 2)
```

`RadiometricAnalyzer` a `SnowDetector` pracují nad `roi_stats`. Moduly, co
skutečně potřebují plné pole (custom PolSAR klasifikace, InSAR fázový rozdíl),
si vyžádají `get_scene_arrays()` — samostatnou, dražší metodu na `DataSource`
rozhraní, volanou jen když je to nutné.

## Update 2026-08-30: živě ověřeno proti CDSE Statistical API

OAuth2 client_credentials flow i Statistical API request/response kontrakt
jsou teď ověřené živým voláním (ne jen psané z paměti). Dva reálné problémy
nalezené a opravené při prvním testu:

1. **`resx`/`resy` jsou v jednotkách bounds CRS.** S `EPSG:4326` (stupně) a
   `resx=10` spadlo celé AOI (~0,7×0,7 km) do jediného pixelu
   (`sampleCount=1`, `stDev=0`, `p10==p90==mean`) — API to nevrátilo jako
   chybu, jen jako fyzikálně nesmyslná data, což je zákeřnější než 400.
   Oprava: `utils/reproject.py` přepočítá AOI do metrického UTM před
   voláním. Po opravě `sampleCount≈4600` pro tuto AOI, hodnoty v
   plausibilním rozsahu.
2. Statistical API vyžaduje explicitní `dataMask` output v evalscriptu
   (`setup()`), jinak 400. A percentily nejsou v odpovědi default — musí se
   vyžádat přes `calculations.default.statistics.default.percentiles`.

Živý test proti mock AOI (Českomoravská vrchovina, ne ověřené zemědělské
pole) vrátil `mean_backscatter_vv_db ≈ -6.3 dB` — nad referenční mokrou
hodnotou (-8.0 dB) z master planu, tedy `relative_moisture_pct` sedí na
stropu 100 %. To je pravděpodobně les/smíšený terén v testovací AOI, ne
chyba výpočtu — modul explicitně neplatí pro hustou vegetaci. **Nejde to
brát jako validaci fyziky** — na to potřebujeme reálný LPIS blok a
porovnání s Intersucho.cz (viz master_plan.md Fáze 1, Den 5).

Zůstává neověřeno/otevřené: `orbit_direction` není v odpovědi Statistical
API, vrací se jako `"UNKNOWN"`; přesné chování na velkých AOI (nad
`MAX_AOI_HA=2000`) neotestováno; skutečný Refined Lee speckle filtr pořád
chybí (viz oprava níže).

## Co to stojí

- Pomalejší start než GEE (žádné hotové `reduceRegion` pohodlí zabudované do
  jednoho volání — Statistical API vyžaduje evalscript a trochu víc nastavení
  OAuth2 client_credentials flow).
- Uživatel (CEO) musí zaregistrovat CDSE účet a vygenerovat OAuth2 client
  credentials na https://dataspace.copernicus.eu (Settings → OAuth clients) —
  toto nejde udělat automatizovaně za něj.

## Co to řeší

- Sovereignty pozice z sekce 5 dokumentu je pravdivá od prvního řádku kódu,
  ne až po budoucím refactoru.
- Speckle filtering NENÍ tímto rozhodnutím vyřešen — viz oprava výše. Pro
  Fázi 1 zmírňujeme šum agregací přes percentily/více scén (viz radiometric.py),
  skutečný per-pixel filtr je otevřená položka pro fázi 1.5/2.
- `preprocessing/calibration.py` a `terrain_correction.py` z master plánu dávají
  smysl (CDSE raw/GRD produkty je potřebují) — u GEE by byly z velké části
  redundantní, protože GEE je dělá interně.
