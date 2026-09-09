# ADR-004: Agroklimatické indexy (Fáze B zemědělského vertikálu)

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-09-09

## Kontext

Po ADR-003 (nezávislý zdroj kořenové zóny) padla otázka na širší
zemědělský vertikál: osevní plán, doporučení plodin, choroby, zavlažování.
Dohodnutý princip pro celý vertikál: **každá funkce musí stát na reálném
registru nebo ověřeném modelu, ne na vágním AI odhadu** — stejná
disciplína jako u fyzikálního enginu.

Tohle ADR pokrývá první, nejlevnější fázi (B): agroklimatické indexy
počítané z dat, co už máme napojená (ERA5-Land/Open-Meteo, ADR-003),
žádný nový externí zdroj.

## Co je uděláno

`engine/datasources/era5_weather.py` — denní Tmax/Tmin/srážky, stejný
zdroj a bez-autentizace vzor jako `era5_land.py`.

`engine/physics/agroclimate.py` — tři nezávislé indexy:
- **Growing Degree Days** (McMaster & Wilhelm 1997) — kumulativní tepelná
  suma, standardní agrometeorologický vzorec
- **Poslední jarní / první podzimní mráz** — z historie Tmin
- **Srážkový deficit/přebytek** vs. víceletý historický normál

10 unit testů na ručně spočítaných hodnotách (ne jen "proběhlo bez
chyby") + živé ověření přes `/api/agroclimate/summary`.

## Živé ověření — a třetí nezávislé potvrzení sucha

Havlíčkobrodsko, sezóna 1.1.–9.9.2026:

| Index | Hodnota |
|---|---|
| GDD (base 5°C) | 1763 |
| Poslední jarní mráz | 30.4.2026 |
| Srážkový deficit vs. 5letý normál | **-134,2 mm** |

Srážkový deficit -134 mm za 252 dní je **třetí nezávislý signál** ve
stejném směru jako ADR-002 (SAR podhodnocuje sucho) a ADR-003 (ERA5-Land
vlhkost pod 5letým minimem) — jiná fyzikální veličina (srážky, ne
vlhkost půdy), jiný výpočet, stejný závěr. Konvergence tří nezávislých
zdrojů je silnější důkaz než jeden dobře vypadající graf.

## Poctivá omezení

- **`gdd_base_temp=5.0` je default pro obiloviny střední Evropy, NE
  univerzální konstanta.** Kukuřice/slunečnice potřebují vyšší základní
  teplotu (~10°C). API to nechává nastavitelné, ale výchozí hodnota je
  volba, ne fyzikální fakt — stejný typ chyby jako univerzální
  `SIGMA_DRY_REF_DB` v ADR-002, tady zdokumentovaná předem, ne nalezená
  po škodě.
- **~9 km rozlišení ERA5-Land** — mrazová data platí pro širší okolí,
  ne přesně pro mikroklima konkrétního pole (údolí vs. kopec mají různé
  mrazové riziko na vzdálenost stovek metrů, což reanalýza nezachytí).
- **Žádná validace mrazových dat proti reálné meteostanici** — historicky
  se to nedělalo, protože pro tenhle vertikál to je nová práce, ne
  rozšíření něčeho už ověřeného.

## Co je další (fáze C-F, viz diskuze 2026-09-09)

C — půdní vhodnost přes BPEJ registr (VUMOP), D — osevní plán a EU CAP
diverzifikační compliance (rule-based), E — chorobové modely tažené
počasím (Smith Period a obdobné), F — zavlažování (FAO-56
Penman-Monteith). Žádné z toho není dnes uděláno.
