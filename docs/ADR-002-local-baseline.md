# ADR-002: Lokální historická dry/wet baseline místo globálních konstant

**Stav:** Přijato, cross-field srovnání zamítnuto jako metodologicky
nevhodné, čeká na multi-sensor korekci | **Datum:** 2026-08-30

Souhrnná verze tohoto dokumentu (case study pro netechnickou/investorskou
audienci) je publikovaná jako artefakt "Ground Truth" — stejná fakta, jiná
forma.

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

## Rozšířená validace: 2 další pole (2026-08-30)

Aby n=1 nezůstalo jediným důkazem, přidána validace na dvou dalších reálných
LPIS polích proti druhému nezávislému Intersucho.cz dotazu:

| Pole | Region | Typ | Local moisture % | Severity | Intersucho ground truth |
|---|---|---|---|---|---|
| ArableLand 672112801/4 (35.6 ha) | Havlíčkobrodsko | orná půda | 68.8 % | mild | "výjimečné až extrémní sucho" |
| ArableLand 694096602/17 (5.4 ha) | Liberecko | orná půda | 57.9 % | mild | "výrazně lepší stav" než Havlíčkobrodsko |
| PermanentGrassland 671112507 (0.79 ha) | Havlíčkobrodsko (stejný region) | trvalý travní porost | 53.8 % | moderate | (mimo dokumentovanou platnost modulu) |

**OPRAVA (automatizovaný test to odhalil, ne ruční kontrola):** Původní
verze tohodle ADR tady tvrdila "relativní řazení mezi regiony sedí" — to
byla chyba v mém vlastním srovnání, ne ve výsledcích. Porovnal jsem
grassland (suchý region) s arable (kontrolní region), tedy dvě různé
kultury napříč regiony, a z toho odvodil závěr o regionech. Když se
porovná arable-to-arable (`tests/integration/test_cdse_live.py::
test_drought_region_field_flags_higher_severity_than_control`), test
PADÁ: suchý region (68.8 %) vyšel **vlhčí** než kontrolní region
(57.9 %) — opačně, než by mělo být.

To relativizuje hypotézu "měříme jen jinou hloubku" — nejde ji brát jako
prokázanou. Otevřené alternativní vysvětlení: obě pole jsou geograficky
daleko od sebe (jiné relativní oběžné dráhy, jiný lokální úhel dopadu),
a `HistoricalBaselineCalculator` mixuje ascending/descending orbity bez
incidence-angle korekce (viz "Zbývající..." níže) — to je konfound,
který se dřív skrýval v jednom poli a teď se ukázal přidáním druhého.
Regresní test je ponechán ve stavu FAILED s `xfail` a důvodem, ne smazán
ani obrácen na tichý pass — dokumentuje otevřený problém, ne fixed stav.

## Pokus o opravu: sezónní okno napříč lety (2026-08-30, pokračování)

Hypotéza po nálezu z předchozí sekce: `HistoricalBaselineCalculator` bral
prostý rolling 365denní lookback, který u kontrolního pole namíchal do
percentilu měsíce s Ïƒâ° kolem -4 až -6 dB (srpen–říjen 2025) — extrémně
vysoké, typické pro hustou vegetaci v plné biomase (objemový rozptyl, ne
vlhkost), zatímco duben–srpen 2026 mělo -10 až -12 dB, srovnatelné se
suchým polem. Potvrzeno měsíčním rozpadem historie obou polí.

**Oprava:** `HistoricalBaselineCalculator` přepsán ze `lookback_days` na
sezónní okno (`seasonal_window_days=21`) napříč `lookback_years=5` lety,
**nikdy z aktuálního roku** (jinak by probíhající sucho zředilo vlastní
referenci). Metodologicky správný postup — odpovídá tomu, jak se dělá
srovnání "stejné období, jiné roky" v remote sensingu obecně.

**Výsledek: cross-field regresní test (`test_drought_region_field_flags_
higher_severity_than_control`) PŘESTO PADÁ DÁL** (61,5 % vs. 51,9 %, pořád
obráceně). Osevní postup mění plodinu na poli rok od roku — i "stejné
kalendářní okno napříč lety" může místo počasí zachytávat střídání plodin
(letos ozimá pšenice v srpnovém okně, loni kukuřice ve stejném okně).
Sezónní korekce je nutná podmínka, ne dostatečná.

## Metodologický obrat: relative_moisture_pct není cross-field metrika

Klíčové zjištění, který posunul celé vyšetřování: **syrová data byla celou
dobu ve správném směru.** Aktuální Ïƒâ° kontrolního pole (-8,61 dB) je
skutečně méně záporné (vlhčí) než suchého pole (-10,24 dB) — to je fyzikálně
správně. Problém nebyl v datech ani ve volbě okna. Problém byl v testu
samotném: `relative_moisture_pct` je z podstaty **relativní anomálie vůči
vlastní historii jednoho místa** (TU Wien Soil *Water Index* — index, ne
absolutní vlhkost), ne absolutní, mezi poli srovnatelná veličina. Dvě pole s
různou půdou/plodinou mají různě široký přirozený dynamický rozsah Ïâ°, takže
68 % u pole A a 58 % u pole B nejsou stejná fyzikální jednotka.

**Rozhodnutí:** cross-field regresní test zůstává `xfail(strict=True)` s
touhle poznámkou — dokumentuje, že se ptal na metodologicky nevhodnou věc,
ne že čeká na budoucí opravu kódu. Validace se přesměrovala na to, co metoda
skutečně měří: vývoj JEDNOHO pole v čase.

**Časová validace** (`relative_moisture_pct` suchého pole napříč 2026,
vlastní sezónní reference pro každé datum):

| Datum | Vlhkost | Severity |
|---|---|---|
| 2026-04-15 | 20,5 % | severe |
| 2026-05-15 | 26,0 % | severe |
| 2026-06-15 | 62,5 % | mild |
| 2026-07-15 | 75,1 % | none |
| 2026-08-15 | 19,3 % | extreme |
| 2026-08-30 | 61,5 % | mild |

Tohle NENÍ čistý, hladce klesající trend odpovídající prohlubujícímu se
suchu — je to šum. Skok z 19,3 % na 61,5 % během 15 dní není důvěryhodná
fyzika povrchové vrstvy, je to signál nestabilního percentilového odhadu
na malém vzorku (±21denní okno × 5 let dává často jen 40–90 scén). Tohle je
POSLEDNÍ otevřená vrstva zjištěná dnes — neopravena, zdokumentována.

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
2. `HistoricalBaselineCalculator` se dnes počítá on-demand (řádově sekundy
   až nízké desítky sekund per request, K let × ~6týdenní okno) — před
   produkčním nasazením nutně cachovat per-AOI (Fáze 3, Supabase).

## Co je skutečně potřeba k uzavření (aktualizováno po sezónní/temporal iteraci)

1. **Multi-sensor fúze (Sentinel-2 NDVI)** — operacionalizovat "NEPLATÍ PRO
   hustou vegetaci" jako skutečné hradlo: vyřadit z historické reference i
   z aktuálního okna scény, kde NDVI ze stejného období indikuje hustý
   porost, místo aby to zůstalo jen věta v docstringu.
2. **Delší archiv / víc let** — zúžit interval spolehlivosti percentilového
   odhadu, který dnes na úzkém sezónním okně dává nestabilní časovou řadu
   (viz sekce výše).
3. **Per-pixel s incidence-angle korekcí** — skutečná TU Wien implementace
   pracuje na úrovni pixelu, ne zonální statistiky přes celé AOI, a
   normalizuje na referenční úhel dopadu. Naše zonální statistika mixuje
   ascending/descending orbity bez korekce.
4. **Víc validačních polí** — tři pole a jeden region nestačí na statistický
   závěr o volbě percentilu ani o tom, jestli je metodika obecně platná.
