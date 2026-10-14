# PhasQ — stav a plán

Živý dokument, aktualizovaný průběžně. Poslední update: 2026-10-14 (bezpečnostní audit).

---

## Bezpečnostní audit 2026-10-14

**Hotovo (branch `security-hardening` v phasq-engine i phasq_app, pushnuto, NEmergnuto):**
- `PetrZakcs/phasq` (veřejné repo s hardcoded hesly/JWT klíči) → **privátní**. Živě ověřeno: Render backend neexistuje, Python API na Vercelu vrací 404 → přihlášení `password123` nikde živě nedostupné. Hodnoty z historie přesto brát jako kompromitované.
- phasq_app: RLS migrace `20261014000000_security_hardening.sql` (uživatel si dřív mohl sám nastavit tarif/kvótu, přepsat výsledek analýzy, padělat audit), atomický start analýzy, auth na všech `/api/*`, odstraněn OpenAI orchestrator + natvrdo datum 2026-06-09, bezpečnostní hlavičky.
- phasq-engine: fail-closed auth (`compare_digest`), validace vstupů (data, Polygon, limit 2000 ha všude, `lookback_years` ≤ 30), upstream chyby jen do logu, sdílený CDSE token.

**Čeká na Petra:**
- Spustit migraci `20261014` na produkční Supabase + nastavit `SUPABASE_SERVICE_ROLE_KEY` (Vercel + `.env.local`) — **bez toho appka po merge nespustí analýzu**.
- Ověřit RLS na tabulce `waitlist` (projekt webu phasq.com) — v repu je `disable_rls.sql`.
- Rozhodnout o simulovaných analýzách (NDVI/NDWI/PolSAR/InSAR generují vymyšlená agronomická doporučení), falešném „API klíči“ v nastavení a mock PDF.

---

## ⚠️ Dřívější priority (stav k 2026-10-14)

1. ~~`phasq-engine` nemá GitHub remote~~ — vyřešeno, privátní `PetrZakcs/phasq-engine`.
2. Appka: integrace enginu pořád jen na branchi `phasq-engine-integration`, `main` pozadu, nic nenasazeno.
3. **Rozpor "500 ha pilot" z investorského decku** — pořád otevřené.
4. ~~Leaknuté heslo v `phasq-master` repu veřejně~~ — repo zprivatizováno 2026-10-14; rotace secretů viz výš.

---

## Co je hotové a živě ověřené

### Fyzikální engine (`phasq-engine`)

**Radiometrická analýza vlhkosti půdy (Sentinel-1 SAR)**
- `Sentinel1CDSESource` — CDSE Statistical API, OAuth2, živě ověřeno (ADR-001)
- `HistoricalBaselineCalculator` — lokální dry/wet reference, sezónní okno napříč lety, medián-z-let, NDVI hradlo (ADR-002, **od 2026-10-01 konečně skutečně zapojené v API — viz ADR-007**)
- `RadiometricAnalyzer` — vlhkost, trend, drought severity, fail-safe na `global_fallback` když chybí data
- Oprava chyby průměru v dB škále — časově (master plan chyba #3) i prostorově přes pixely (ADR-007, nalezeno externí review)
- Oprava `valid_pixel_ratio` na `(sampleCount-noDataCount)/geometryPixelCount` (ADR-007)

**Kořenová zóna — dva nezávislé signály**
- `root_zone.py` — SWI filtr (Wagner 1999) nad SAR signálem. Omezení: resetuje se při každém volání — neřešeno
- `nasa_power_rootzone.py` — NASA POWER/GWETROOT, zdarma natrvalo, ~10denní zpoždění, viditelně přiznané (ADR-006)

**Agroklimatika (Fáze B zemědělského plánu)**
- `nasa_power_weather.py` + `agroclimate.py` — GDD, mrazová data, srážkový deficit, NASA POWER, zdarma
- `/api/agroclimate/summary`

**Mapový podklad**
- `sentinel2_truecolor.py` — CDSE Process API, nahrazuje Esri (ADR-005)
- `/api/imagery/truecolor`

**Testy:** 37/37 unit testů zelených (čistá instalace, `pytest-asyncio==0.23.8`)

**ADR dokumenty:** ADR-001 až ADR-007 v `docs/` — kompletní historie rozhodnutí, živých nálezů, a vlastních chyb

### Appka (`phasq_app`)

- **Bezpečnost:** `getSession()` → `getUser()` napříč middleware + API routes
- **Produkční Supabase** obnovena, 2 opravené DB bugy (INTEGER kvóta, chybějící `audit_log` INSERT policy)
- **phasq-engine napojen** — reálná analýza uložená v produkční DB
- **Mapový podklad** — Esri (zakázané komerčně) → CDSE Sentinel-2 + NASA GIBS
- **Živý důkaz:** reálný uživatel, reálné pole (LPIS geometrie), reálná analýza v produkci — **POZOR: s dnešními opravami (ADR-007) dává tahle konkrétní analýza jiný, méně uspokojivý výsledek (viz níže), potřeba přepočítat**

### Case study
- Artefakt "Ground Truth" — publikovaný. **Potřeba aktualizovat po ADR-007 zjištění** — uvedená čísla (56,4 %/"mírné") vznikla s NDVI hradlem, co ve skutečnosti neběželo.

---

## Co jsme dnes zjistili (2026-10-01) — vážné, ne kosmetické

Externí review (druhý agent) + moje nezávislé ověření odhalily 4 reálné bugy v enginu, všechny opravené:
1. dB počítáno před prostorovou agregací místo po — **živě ověřený rozdíl 0,624 dB**
2. `valid_pixel_ratio` špatný vzorec — živě ověřený rozdíl ~8 procentních bodů
3. **NDVI hradlo nikdy neběželo v živém API**, jen v izolovaných testech, přes vlastní tvrzení "hotovo, funguje" v ADR-002
4. `pytest-asyncio==0.23.0` padá na čisté instalaci

**Nepříjemný důsledek opravy #3:** se skutečně zapojeným NDVI hradlem lokální baseline na našem vlajkovém validačním poli **spadla na globální fallback** — NDVI práh (0,35) vyřadil 35 scén jako "hustou vegetaci" (ozimá pšenice i ve vodním stresu má NDVI přes 0,35), zbyly jen 2 kvalifikované roky z 5. Výsledek (89 % / "none") je DÁL od Intersucho reality než náš dřívější chybný výsledek. **Nikdy jsme neměli jeden plně správně zapojený běh celé metodiky, co by dal uspokojivý výsledek na reálném poli.** Viz ADR-007.

---

## Co je otevřené, poctivě

| # | Co | Poznámka |
|---|---|---|
| 1 | **NDVI práh aktivně blokuje validaci** | nová priorita po ADR-007 — potřeba rekalibrovat nebo nahradit |
| 2 | Kontinuální SWI stav | SAR-only, žádný nový zdroj — nezačato |
| 3 | Leaknuté heslo (`phasq-master` repo) | čeká na potvrzení |
| 4 | Git zálohy obou repozitářů | viz priority nahoře |
| 5 | "500 ha pilot" rozpor | viz priority nahoře |
| 6 | Žádná kvantitativní validace (korelace/RMSE) | jen kvalitativní srovnání na 3 polích |
| 7 | Žádný in-situ ground truth | Intersucho i NASA POWER jsou taky modely, ne senzor v zemi |
| 8 | Žádná prostorová (per-pixel) analýza | jen průměr přes celé pole |
| 9 | Žádná VH/VV, žádná korekce úhlu dopadu | zdokumentováno, neřešeno |
| 10 | Orba/sklizeň mění referenci, nerozpoznáno | živě nalezený, nevyřešený jev |
| 11 | Živé nasazení | appka běží jen lokálně |
| 12 | LPIS WFS bug (`mze_lpis:dpb`) | špatný typeName |
| 13 | `npm audit` (2 kritické, 6 vysoké) | zjištěno, neprozkoumáno |
| 14 | "Multiple GoTrueClient instances" | logout bug obcházen, kořen nenalezen |

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

## Čeká na rozhodnutí (ne na mě)

- **Monorepo + Vercel nasazení** (návrh druhého agenta) — technicky solidní plán (git subtree, dva Vercel projekty, region fra1), ale je to větší/méně vratná operace. Čeká na tvoje explicitní ano.
- **Co přesně tvrdí investorský deck** — potřebuju vědět, abych zjistil rozsah rozporu s realitou.
