# ADR-011: NDVI práh jako parametr + živě naměřený dopad (Fáze 0, engine/trafficability)

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-10-13

## Pozn. k číslování

Zadání pro `engine/trafficability` explicitně rezervuje `ADR-011` pro
ověření nových datových zdrojů (fáze 1), `ADR-012` pro klasifikační
logiku (fáze 2) a `ADR-013` pro validační kritéria (fáze 3) - ale
nenechává číslo pro Fázi 0 (NDVI práh), přestože fázová tabulka
explicitně žádá vlastní ADR jako "hotovo" kritérium. Řazeno
chronologicky: tahle ADR je `ADR-011`, následující tři se tím posouvají
na `ADR-012` (datové zdroje), `ADR-013` (klasifikace), `ADR-014`
(validační kritéria). Stejný typ kolize jako `ADR-008`/`ADR-009` dřív v
`engine/ki/` - řešeno stejně (další volné číslo, nahlášeno Petrovi).

## Kontext

`ADR-007` a `ADR-008` už zdokumentovaly, že `DENSE_VEGETATION_NDVI_THRESHOLD=0.35`
je "nekalibrovaný, ne vyladěný na naše pole" a že jeho zapnutí shazuje
lokální baseline na `global_fallback` i na vlajkovém validačním poli.
`engine/trafficability` na tom přímo staví (`RadiometricAnalyzer`,
`HistoricalBaselineCalculator`) - bez funkční lokální baseline bude
většina polí ve třídě "Nelze určit", což zadání samo označuje za
hlavní riziko.

## Rozhodnutí

`NDVISample.is_dense_vegetation` je teď metoda s parametrem `threshold`
(výchozí = `DENSE_VEGETATION_NDVI_THRESHOLD`, chování beze změny),
`HistoricalBaselineCalculator` má nový konstruktorový parametr
`dense_vegetation_ndvi_threshold` (výchozí stejná konstanta). `LocalReference`
teď nese `dense_vegetation_ndvi_threshold_used` (`None`, když NDVI hradlo
vůbec neběželo) - traceable, ne tichá hodnota.

**Výchozí hodnota se neměnila** - volající kód bez argumentu se chová
přesně jako dřív (zadání: "s výchozí hodnotou = dnešní chování").

## Živě naměřený dopad (3 pole, `AS_OF=2026-09-09`, stejné datum jako ADR-007 pro srovnatelnost)

| Pole | 0,35 (dnešní) | 0,5 | 0,6 |
|---|---|---|---|
| `arable_field` (vlajkové z ADR-007) | **FALLBACK** (35 scén vyřazeno, jen 2 roky kvalifikované) | **OK** (dry=-11,09, wet=-8,68, 4 roky, 5 vyřazeno) | **OK** (dry=-10,98, wet=-8,26, 5 let, 0 vyřazeno) |
| `arable_north` | OK (dry=-10,71, wet=-4,75, 4 roky, 33 vyřazeno) | OK (dry=-11,26, wet=-4,86, 5 let, jen 2 vyřazeno) | OK (dry=-11,26, wet=-4,94, 5 let, 0 vyřazeno) |
| `grassland` | **FALLBACK** (53 vyřazeno, jen 1 rok) | **FALLBACK** (51 vyřazeno, jen 1 rok) | **FALLBACK** (40 vyřazeno, jen 2 roky) |

### Nález 1: 0,5 opravuje `arable_field` (ten samý z ADR-007/ADR-008)

Práh 0,5 místo 0,35 stačí na to, aby vlajkové pole z ADR-007 konečně
dostalo `local_baseline` místo `global_fallback`. Fyzikálně to dává
smysl - ozimá pšenice v regionu běžně dosahuje NDVI 0,35-0,5 i ve fázích,
kdy půda pod porostem ještě není "plně zapojená vegetace" ve smyslu,
pro který byl 0,35 původně zvolen (literatura pro PLNOU vegetační
pokrývku, ne pro střední růstovou fázi).

### Nález 2: NIC v rozsahu 0,35-0,6 neopravuje `grassland`

Tohle je důležitější zjištění než nález 1. Trvalý travní porost má NDVI
trvale vysoké (ne sezónní špička jako u plodiny) - i při 0,6 zůstává
vyřazeno 40 z ~90 scén a kvalifikují se jen 2 roky (potřeba 3,
`MIN_YEARS_FOR_MEDIAN`). Zvyšování prahu dál by začalo propouštět
scény, co už nejsou "půda pod řídkou vegetací" v žádném smysluplném
smyslu - fyzikální předpoklad change detection metody (TU Wien,
Bauer-Marschallinger 2019) pro holou/řídce vegetovanou půdu u louky
prostě sedí hůř než u orné půdy.

**Důsledek pro `engine/trafficability`:** zadání (kap. 4, pravidlo 1)
počítá s "orná půda NEBO louka" jako rozsahem v1 - louka v tomhle
rozsahu zůstane realisticky většinou ve třídě "Nelze určit"
(`global_fallback` → `ADR-008` pravidlo), ne proto, že by klasifikační
logika chybovala, ale protože NDVI-hradlovaná change detection metoda
na louky fyzikálně špatně sedí. Tohle NENÍ bug k opravení v rámci
Fáze 0 - je to limit metody, co patří do `caveat` pole výstupu, ne
něco, co by šlo "doladit prahem".

## Doporučení pro `engine/trafficability`

`HistoricalBaselineCalculator` volat s `dense_vegetation_ndvi_threshold=0.5`
pro ornou půdu (zlepšuje `arable_field` i `arable_north`, u žádného z
obou polí nezhoršuje). Pro louku nečekat zlepšení - честně reportovat
jako limit metody, ne jako chybějící parametr.

**Systémový default (`DENSE_VEGETATION_NDVI_THRESHOLD=0.35` v
`sentinel2_cdse.py`) se NEMĚNÍ** - zůstává neutrální výchozí hodnota pro
cokoliv, co parametr explicitně nepředá (agrokultura v `phasq_app`
zůstává beze změny chování). `engine/trafficability/run.py` předá
`0.5` explicitně.

## Testy

`tests/test_baseline.py`: 3 nové testy (`test_default_ndvi_threshold_unchanged_behavior`,
`test_higher_ndvi_threshold_keeps_dense_scenes_and_changes_reference`,
`test_threshold_used_is_none_without_ndvi_source`) + nový `tests/fixtures/fake_ndvi_source.py`.

65/65 testů zelených (62 původních beze změny + 3 nové).
