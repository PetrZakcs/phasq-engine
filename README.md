# phasq-engine

Python FastAPI fyzikální SAR analytický engine pro PhasQ. Bere Sentinel-1 data,
vrací deterministická, fyzikálně odvozená čísla — žádná generativní AI ve
výpočtu. Kontext a vize: viz `phasq_cto_master_plan.md` v repu `phasq_app`.

**Datový zdroj je Copernicus Data Space Ecosystem (CDSE), ne Google Earth
Engine** — důvod a důsledky v [docs/ADR-001-data-source.md](docs/ADR-001-data-source.md).

## Stav (2026-08-30)

Fáze 1 spike: `Sentinel1CDSESource` + `RadiometricAnalyzer` fungují proti
mock datům i **živě proti CDSE Statistical API** (ověřeno reálným voláním,
ne jen testy). Detaily a dvě chyby nalezené/opravené při prvním live testu
(CRS jednotky resx/resy, chybějící dataMask output) jsou v
[docs/ADR-001-data-source.md](docs/ADR-001-data-source.md).

**Nejde to ale ještě brát jako fyzikálně validovanou analýzu** — testovací
AOI je náhodný čtverec v Českomoravské vrchovině, pravděpodobně les, ne
zemědělská půda, na kterou modul cílí. Další krok: reálný LPIS blok +
porovnání s Intersucho.cz (master_plan.md Fáze 1, Den 5).

Žádná Supabase integrace, žádná perzistence, žádný quota enforcement —
to je Fáze 3 dle master plánu, záměrně zatím chybí. `orbit_direction` se
z Statistical API nevrací (`"UNKNOWN"`), skutečný per-pixel speckle filtr
taky chybí (viz ADR-001).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# vyplň CDSE_CLIENT_ID / CDSE_CLIENT_SECRET — registrace na
# https://dataspace.copernicus.eu, pak Settings -> OAuth clients -> Create new client
```

## Testy (mock data, žádné live credentials potřeba)

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Spuštění lokálně

```bash
source .venv/bin/activate
uvicorn main:app --reload --port 8000
curl http://localhost:8000/api/health
```

## Struktura

Viz `phasq_cto_master_plan.md` sekce 1.3 — struktura je z ní přímo odvozená,
s jednou odchylkou (`SAR_Scene.roi_stats` místo povinné `backscatter_db`
matice), zdokumentovanou v ADR-001.
