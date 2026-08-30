# phasq-engine

Python FastAPI fyzikální SAR analytický engine pro PhasQ. Bere Sentinel-1 data,
vrací deterministická, fyzikálně odvozená čísla — žádná generativní AI ve
výpočtu. Kontext a vize: viz `phasq_cto_master_plan.md` v repu `phasq_app`.

**Datový zdroj je Copernicus Data Space Ecosystem (CDSE), ne Google Earth
Engine** — důvod a důsledky v [docs/ADR-001-data-source.md](docs/ADR-001-data-source.md).

## Stav (2026-08-30)

Fáze 1 spike: `Sentinel1CDSESource` + `RadiometricAnalyzer` fungují proti
mock datům (viz `tests/`). **Live volání proti CDSE Statistical API zatím
NENÍ ověřeno** — přesný JSON kontrakt v `engine/datasources/sentinel1_cdse.py`
je psán z paměti a označen TODO komentáři. První reálný test s platnými
credentials tohle buď potvrdí, nebo (pravděpodobněji) bude vyžadovat úpravu
payloadu/parsování podle skutečné odpovědi API.

Žádná Supabase integrace, žádná perzistence, žádný quota enforcement —
to je Fáze 3 dle master plánu, záměrně zatím chybí.

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
