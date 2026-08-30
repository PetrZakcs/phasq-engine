# Data pro case study — živě ověřeno 2026-08-30

Všechna čísla níže jsou z reálných API volání proti CDSE (Copernicus Data
Space Ecosystem) a reálným LPIS polím, ne mock data. Zdroj u každého bloku.

---

## 1. Testovací pole (reálná, z veřejného LPIS registru MZe ČR)

| Pole | LPIS ID | Plocha (LPIS) | Plocha (naše aproximace) | Region | Kultura |
|---|---|---|---|---|---|
| A — "suché" | `672112801/4` | 35,64 ha | 35,61 ha (odchylka 0,08 %) | Havlíčkobrodsko (Vysočina) | Orná půda |
| B — "kontrolní" | `694096602/17` | 5,41 ha | — | Liberecko | Orná půda |
| C — travní porost | `671112507` | 0,79 ha | — | Havlíčkobrodsko | Trvalý travní porost |

Zdroj geometrie: `gis.cenia.cz/geoserver/mze_lpis/wfs`, vrstva
`mze_lpis:agriculturalarea` (živé, veřejné, bez autentizace).

---

## 2. Nezávislý ground truth (Intersucho.cz, 23.–30. 8. 2026)

> Havlíčkobrodsko a Žďársko patří mezi lokality s "výjimečným až extrémním
> suchem" v profilu půdy 0–100 cm. Velmi nízká vlhkost půdy pod 30 % VVK
> na 55 % stanic v hloubce 50–100 cm.

> Severní Čechy (Liberecko): "Vyšší vlhkosti registrujeme především v
> horských polohách na severu Čech" — výrazně lepší stav než Havlíčkobrodsko.

Zdroj: www.intersucho.cz, dotaz 2026-08-23 a 2026-08-30.

---

## 3. Klíčové srovnání: globální vs. lokální kalibrace (pole A)

| | Ïƒâ° (aktuální) | Referenční škála | Vlhkost | Verdikt |
|---|---|---|---|---|
| Globální konstanty (starý model) | -10,24 dB | -22 / -8 dB (fixní) | **84,0 %** | žádné riziko |
| Lokální baseline (365 dní, 188 scén) | -10,24 dB | -13,72 / -8,66 dB | **68,8 %** | mírné sucho |

Analytické okno: 16.–30. 8. 2026, 6 scén Sentinel-1.

---

## 4. Živá Sentinel-1 časová řada — pole A, 16.–30. 8. 2026 (VV, dB)

| Datum | Ïƒâ° VV (dB) |
|---|---|
| 2026-08-18 | -10,29 |
| 2026-08-20 | -9,70 |
| 2026-08-21 | -9,61 |
| 2026-08-24 | -10,78 |
| 2026-08-26 | -10,86 |
| 2026-08-27 | -10,34 |

---

## 5. Přesnost výpočtu plochy AOI

Naše ekvirektangulární aproximace (`polygon_area_ha`) proti oficiální LPIS ploše:

- Vypočteno: 35,61 ha
- LPIS oficiálně: 35,64 ha
- **Odchylka: 0,08 %**

---

## 6. Multi-year stabilita lokální reference (pole A)

| Historie | Suchá reference (dB) |
|---|---|
| 1 rok | -13,72 |
| 2 roky | -13,60 |
| 4 roky | -13,52 |

Prakticky identické napříč roky — referenční škála pole je stabilní vlastnost
pole, ne náhoda krátkého období.

---

## 7. Odhalený bug v CDSE API integraci (transportní vrstva)

Před opravou: `resx`/`resy` parametry poslány v jednotkách EPSG:4326
(stupně) místo metrů → celé AOI (~35 ha) se sesbíralo do **1 pixelu**.

- Před opravou: `sampleCount: 1`, průměr +2,6 dB (fyzikálně nesmyslné)
- Po opravě (reprojekce do UTM): `sampleCount: 5600`, průměr v rozumném
  rozsahu (-6 až -13 dB dle scény)

---

## 8. NDVI ověření (Sentinel-2, pole B, anomální období)

| Datum | Ïƒâ° VV (dB) | NDVI |
|---|---|---|
| 2025-08-28 | -13,12 | 0,137 |
| 2025-08-30 | -5,26 | 0,137 |
| 2025-08-31 | -3,47 | 0,137 |
| 2025-09-18 | -4,42 | 0,307 |

NDVI nízké a klesající přesně v okamžiku extrémního nárůstu Ïƒâ° — vylučuje
hypotézu "hustá vegetace" jako příčinu.

---

## 9. Testovací pokrytí

- **14/14** unit testů zelených (`pytest tests/ --ignore=tests/integration`)
- **2 passed, 1 xfailed** (živé integrační testy proti CDSE, `pytest tests/integration/`)
- Klíčové testy:
  - `test_mean_backscatter_db_averages_in_linear_scale` — hlídá chybu průměru v dB škále
  - `test_one_anomalous_year_does_not_dominate_reference` — hlídá odolnost proti anomálnímu roku
  - `test_area_calc_matches_lpis_official_area` — živě ověřuje přesnost plochy
  - `test_never_includes_current_year` — hlídá, že se aktuální rok nikdy nepočítá do reference

---

## 10. Architektura (fakta k referenci)

- **Datový zdroj:** Copernicus Data Space Ecosystem (CDSE), ne Google Earth
  Engine — sovereignty-first rozhodnutí (EU infrastruktura, OVHcloud Francie)
- **Metoda:** TU Wien change detection (Bauer-Marschallinger et al. 2019),
  lokální per-AOI baseline, medián z ročních percentilů
- **Repo:** `phasq-engine`, moduly `RadiometricAnalyzer`,
  `HistoricalBaselineCalculator`, `Sentinel1CDSESource`, `Sentinel2NDVISource`
- **Dokumentace:** `docs/ADR-001-data-source.md`, `docs/ADR-002-local-baseline.md`
  (kompletní technický log s časovými razítky)

---

## Co je ověřené vs. co zůstává otevřené (pro poctivost v case study)

**Ověřeno živě:**
- Transportní vrstva (OAuth2, CDSE Statistical API)
- Přesnost výpočtu plochy (0,08 % odchylka)
- Lokální baseline > globální konstanta (měřitelné zlepšení)
- Stabilita reference napříč lety
- Odolnost proti jednomu anomálnímu roku

**Otevřené (nezakrývat v case study):**
- Cross-field srovnání (metodologicky mimo rozsah metody)
- Kalibrace NDVI prahů (jen 2-3 pole, ne statisticky významný vzorek)
- Přesná příčina anomálií (drsnost povrchu vs. mokrá půda — nerozlišeno)
- Hloubka měření: Sentinel-1 VV vidí ~0-5 cm, Intersucho profil 0-100 cm
