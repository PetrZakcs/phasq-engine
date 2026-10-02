# ADR-008: global_fallback už nikdy nevydává verdikt

**Stav:** Přijato, testováno | **Datum:** 2026-10-02

## Kontext

Druhý agent (nezávislá review po ADR-007) upozornil na architektonickou
chybu, která přežila i po opravách z ADR-007: `RadiometricAnalyzer.analyze()`
počítal `drought_severity`/`drought_risk` úplně stejně bez ohledu na to,
jestli `reference_source` je `local_baseline`, nebo `global_fallback` — jediný
rozdíl byla jedna věta schovaná uvnitř `alert_message`.

To je přesně ta samá třída chyby, co ADR-002 už jednou živě odhalilo:
globální konstanty (`SIGMA_DRY_REF_DB=-22`, `SIGMA_WET_REF_DB=-8`) daly
reálnému poli "84 % vlhkost, no drought" během nezávisle potvrzeného
extrémního sucha (Intersucho.cz). ADR-007 to potvrdilo znovu — jakmile
NDVI hradlo skutečně běží, vlajkové validační pole spadne na
`global_fallback` a dostane "89 %, none" — DÁL od reality než předchozí
vadný běh.

## Rozhodnutí

Když `reference_source == "global_fallback"`:
- `drought_severity = "unknown"` (ne vypočtená hodnota ze `SEVERITY_THRESHOLDS_PCT`)
- `drought_risk = None` (ne `True`/`False`)
- `alert_message` explicitně říká "Nelze spolehlivě vyhodnotit riziko sucha"
- `relative_moisture_pct` ZŮSTÁVÁ v odpovědi — syrové, orientační číslo
  z globálních konstant pořád má informační hodnotu, ale přestává se tvářit
  jako verdikt

Verdikt (`drought_severity`/`drought_risk` jiné než `unknown`/`None`)
existuje JEN když je `reference_source == "local_baseline"`.

## Proč ne jinak

Zvažovaná alternativa: nechat `global_fallback` dál počítat verdikt, jen
přidat pole `verdict_reliable: bool`. Zamítnuto — stejné selhání jako
schovaná poznámka v `alert_message`: spoléhá na to, že downstream kód
(appka, budoucí API klient) tohle pole skutečně přečte a zohlední. Když
`drought_severity` sám o sobě říká "unknown", není možné ho omylem
vykreslit jako "none"/"mild" bez zjevné chyby v kódu, co to pole ignoruje.

## Dopad na appku

`phasq_app` (`AnalysisDetailView.tsx`) už zobrazuje `reference_source`
badge (LOKÁLNÍ BASELINE / GLOBÁLNÍ FALLBACK) vedle `drought_severity` —
UI teď u `global_fallback` case prostě ukáže "unknown" misto falešně
sebevědomého verdiktu, žádná změna komponenty nebyla nutná pro tohle
konkrétní pole (zobrazuje, co dostane).

## Testy

`tests/test_radiometric.py`:
- `test_global_fallback_never_emits_verdict` (nový) — přímý regresní test
- `test_drought_detection_extreme`, `test_no_drought_wet_conditions` —
  upraveny, aby testovaly severity logiku přes `local_reference` (jediná
  cesta, co teď verdikt vůbec vydává)
- `test_local_reference_changes_verdict_vs_global_fallback` — upraveno:
  dřív `assert result_global["drought_risk"] is False` (ten samý
  přehnaně sebevědomý verdikt, co tahle ADR opravuje), teď
  `assert result_global["drought_severity"] == "unknown"`
