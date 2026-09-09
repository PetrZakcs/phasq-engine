# PhasQ — stav a plán

Živý dokument, aktualizovaný průběžně. Poslední update: 2026-09-09.

---

## Co je hotové a živě ověřené

### Fyzikální engine (`phasq-engine`)

**Radiometrická analýza vlhkosti půdy (Sentinel-1 SAR)**
- `Sentinel1CDSESource` — CDSE Statistical API, OAuth2, živě ověřeno (ADR-001)
- `HistoricalBaselineCalculator` — lokální dry/wet reference, sezónní okno napříč lety, medián-z-let, volitelné NDVI hradlo (ADR-002)
- `RadiometricAnalyzer` — vlhkost, trend, drought severity, fail-safe na `global_fallback` když chybí data
- Oprava chyby průměru v dB škále (master plan chyba #3), regresní test

**Kořenová zóna — dva nezávislé signály**
- `root_zone.py` — SWI filtr (Wagner 1999) nad SAR signálem. **Omezení: resetuje se při každém volání, netlumí šum mezi voláními** — právě řešíme (viz níže)
- `nasa_power_rootzone.py` — NASA POWER/GWETROOT, zdarma natrvalo, ~10denní zpoždění, viditelně přiznané (ADR-006)

**Agroklimatika (Fáze B zemědělského plánu)**
- `nasa_power_weather.py` + `agroclimate.py` — GDD, mrazová data, srážkový deficit, NASA POWER, zdarma
- `/api/agroclimate/summary`

**Mapový podklad**
- `sentinel2_truecolor.py` — CDSE Process API, nahrazuje Esri (ADR-005)
- `/api/imagery/truecolor`

**Testy:** 37/37 unit testů zelených, integrační testy proti živému CDSE (spouští se ručně)

**ADR dokumenty:** ADR-001 (CDSE místo GEE) až ADR-006 (NASA POWER místo Open-Meteo) — kompletní historie rozhodnutí a živých nálezů v `docs/`

### Appka (`phasq_app`)

- **Bezpečnost:** `getSession()` → `getUser()` napříč middleware + API routes (server-side autorizace)
- **Produkční Supabase** obnovena, reálné schéma, 2 opravené DB bugy (INTEGER kvóta, chybějící `audit_log` INSERT policy)
- **phasq-engine napojen** — `/api/gee/analyze` + `/api/gee/status`, reálná analýza uložená v produkční DB
- **Mapový podklad** — Esri (zakázané komerčně) → CDSE Sentinel-2 (hotová analýza) + NASA GIBS (kreslení AOI)
- **Úklid mrtvého kódu** — `gee-server.ts`, `@google/earthengine`, `mapbox-gl` odstraněny
- **Živý důkaz:** reálný uživatel, reálné pole (LPIS geometrie), reálná analýza v produkci

### Case study
- Artefakt "Ground Truth" — 13 nálezů, dvě kapitoly (fyzikální validace + produkční integrace), publikovaný

---

## Co je otevřené, poctivě

| # | Co | Poznámka |
|---|---|---|
| 1 | Kontinuální SWI stav | **řešíme teď** — SAR-only, žádný nový zdroj |
| 2 | Leaknuté heslo (`phasq-master` repo) | čeká na tvoje potvrzení k vytažení |
| 3 | Živé nasazení | appka běží jen lokálně |
| 4 | LPIS WFS bug (`mze_lpis:dpb`) | špatný typeName, nikdy neopraveno |
| 5 | CENIA LPIS licence | řešíš přímo s MZe |
| 6 | `npm audit` (2 kritické, 6 vysoké) | zjištěno, neprozkoumáno |
| 7 | "Multiple GoTrueClient instances" | logout bug obcházen, kořen nenalezen |
| 8 | Kalibrace fyziky na ~3 polích | cross-field srovnání pořád nefunguje |

---

## Plán pro zemědělský vertikál ("dokončit zemědělství")

| Fáze | Co | Stav |
|---|---|---|
| **A** | LPIS import (geometrie, číselník plodin, farmářův WS klíč) | A1/A2 neopraveno, A3 čeká na MZe |
| **B** | Agroklimatické indexy (GDD, mráz, srážky) | ✅ hotovo |
| **C** | Půdní vhodnost přes BPEJ registr (VUMOP) | nezačato |
| **D** | Osevní plán + EU CAP compliance (rule-based) | nezačato |
| **E** | Choroby/škůdci (epidemiologické modely tažené počasím) | nezačato |
| **F** | Zavlažování (FAO-56 Penman-Monteith) | nezačato |

---

## Právě teď pracujeme na

**Kontinuální SWI stav** — `root_zone.py` dnes počítá SWI filtr znovu od nuly při každém volání `analyze()`. Cíl: uložit stav (poslední SWI hodnota + K-gain + datum) per-AOI mezi voláními, aby filtr skutečně integroval čas, ne jen scény z jednoho okna. Řeší to "poslední otevřenou vrstvu" z ADR-002 (šum mezi měsíčními snímky) — jen ze Sentinel-1, žádný nový externí zdroj.
