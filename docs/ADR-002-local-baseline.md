# ADR-002: Lokální historická dry/wet baseline místo globálních konstant

**Stav:** Přijato, částečně otevřené | **Datum:** 2026-08-30

## Nález (fyzikální validace, master_plan.md Fáze 1 Den 5)

Reálný LPIS blok (ArableLand, ID `672112801/4`, 35.64 ha, Havlíčkobrodsko)
analyzovaný přes `RadiometricAnalyzer` s globálními konstantami
(`SIGMA_DRY_REF_DB=-22`, `SIGMA_WET_REF_DB=-8`) vrátil `relative_moisture_pct
= 84 %`, `drought_risk = false` k datu 2026-08-30.

Intersucho.cz k témuž datu hlásí pro tentýž region **"výjimečné až extrémní
sucho"**, vlhkost pod 30 % VVK na většině stanic. Přímý rozpor.

## Diagnostika

`backCoeff` (GAMMA0_TERRAIN vs SIGMA0_ELLIPSOID) posunul výsledek jen o
~1,4 dB — vedlejší efekt, ne hlavní příčina.

Hlavní příčina: `SIGMA_DRY_REF_DB`/`SIGMA_WET_REF_DB` jsou **jedna pevná
dvojice konstant pro celou střední Evropu**. Metoda, kterou master plán cituje
(Bauer-Marschallinger et al. 2019, TU Wien change detection), ale počítá
**lokální historickou referenci per lokalita** z víceletého archivu — ne
univerzální práh. Roční historie tohoto konkrétního pole má rozpětí jen
-15.71 až -7.98 dB, nikdy se neblíží ke globální -22 dB "suché" referenci.

## Rozhodnutí

`engine/physics/baseline.py`: `HistoricalBaselineCalculator` počítá per-AOI
dry/wet referenci jako p5/p95 percentil z historie `roi_stats.mean_db`
(perioda konfigurovatelná, default 365 dní). `RadiometricAnalyzer.analyze()`
přijímá `local_reference: LocalReference | None` — pokud je k dispozici,
použije se místo globálních konstant, a `reference_source` v response říká
který zdroj byl použit (`local_baseline` vs `global_fallback`).

## Výsledek po opravě (živě ověřeno)

| | mean Ïƒâ° | reference | moisture % | severity |
|---|---|---|---|---|
| Před (global) | -10.24 dB | -22/-8 (fixní) | 84.0 % | none |
| Po (local, 365d, 188 scén) | -10.24 dB | -13.72/-8.66 (lokální) | 68.8 % | mild |

Směr opravy je správný a potvrzený: **multi-year test (1/2/4 roky) dává
prakticky identickou dry referenci** (-13.72 / -13.60 / -13.52 dB) —
vylučuje hypotézu "krátké okno je náhodně zkreslené". Tohle pole má stabilně
jinou přirozenou fyzikální škálu než globální konstanta, ne artefakt jednoho
období.

## Zbývající, NEVYŘEŠENÁ mezera — a proč to není další kalibrační bug

68,8 % / "mild" pořád není "extrémní sucho" z Intersucho. Nejpravděpodobnější
vysvětlení není chyba výpočtu, ale **fyzikální limit měřicí hloubky**:

- Sentinel-1 C-band VV backscatter měří svrchní ~0-5 cm půdy.
- Intersucho.cz klasifikace "extrémní sucho" je za profil 0-100 cm, z
  pozemních stanic + modelu, ne ze samotného SAR.
- Lehký déšť může nasytit svrchní vrstvu (co vidí SAR), zatímco kořenová
  zóna zůstává kriticky suchá (co vidí Intersucho). Tohle je zdokumentovaný
  limit C-band SAR retrieval v literatuře, ne bug v `sentinel1_cdse.py`
  ani v `baseline.py`.

**Rozhodnutí: nehonit další kalibrací na jediném poli.** Jedno pole je n=1,
další ladění konstant proti němu by bylo overfitting. Místo toho:

1. Do API response přidán `measurement_caveat` — stejný vzor jako lavinový
   disclaimer u SnowDetector v master_plan.md 2.2, transparentnost o limitu
   místo předstírání, že SAR nahrazuje hloubkový profil.
2. Před dalším laděním potřebujeme **víc validačních polí** (různé plodiny,
   půdy, regiony) — jedno pole nestačí na závěr, jestli je p5/p95 ta správná
   volba percentilu, nebo jestli je potřeba i incidence-angle korekce
   (aktuálně mícháme ascending/descending orbity bez korekce, což do
   historické distribuce přidává rozptyl nesouvisející s vlhkostí).
3. `HistoricalBaselineCalculator` se dnes počítá on-demand (~4-10s per
   request) — před produkčním nasazením nutně cachovat per-AOI (Fáze 3,
   Supabase), ne přepočítávat při každé analýze.
