# ADR-006: Živá kořenová zóna — ERA5-Land/Open-Meteo → NASA POWER

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-09-09

## Kontext

ADR-003 zavedl ERA5-Land (přes Open-Meteo) jako nezávislý druhý zdroj
kořenové zóny. Živě ověřeno (viz ADR-005), že Open-Meteo zdarma tarif je
**explicitně zakázaný pro komerční použití** — matice na jejich pricing
stránce má u Free tarifu "Commercial use: ❌". Přechod na placený tarif
(~$29/měs za 1M volání) byl na stole, ale zamítnut ve prospěch řešení
bez jakékoliv nové registrace/platby.

## Zvažované cesty

1. **CDS API přímo** (oficiální Copernicus zdroj ERA5-Land) — zdarma i
   komerčně (CC-BY), ale pravděpodobně asynchronní job-queue architektura,
   vyžaduje registraci, neznámá latence — neověřeno živě.
2. **Zaplatit Open-Meteo** — jednoduché, ale je to přesně ten vzor
   "odložit problém, až budou peníze", co jsme si v tomhle projektu
   opakovaně zakázali (leaknuté heslo, DB bugy — věci co se objeví
   v nejhorší chvíli, když se odkládají).
3. **NASA POWER (GWETROOT)** — zdarma pro cokoliv, natrvalo, bez
   registrace. Cena: ~9-10denní zpoždění (živě ověřeno).

**Rozhodnutí: NASA POWER.** Ne kompromis kvůli penězům — řešení, co
nikdy nebude potřeba měnit, až firma vydělá.

## Živé ověření

Stejné pole jako ADR-003 (Havlíčkobrodsko), k datu 2026-09-09:

| | ERA5-Land (ADR-003, Open-Meteo) | NASA POWER (tohle ADR) |
|---|---|---|
| Veličina | m³/m³ | frakce nasycení 0-1 (GWETROOT) |
| Aktuální hodnota | 0.185 | 0.39 (k 30.8., ne k 9.9.) |
| Historický percentil | 0,0 % | 0,0 % |
| Pod historickým minimem | ano | ano |
| Zpoždění | ~0 dní | **~10 dní** |

Stejný závěr (pod 5letým minimem), jiná reanalýza (MERRA-2 vs. ERA5),
nezávislé potvrzení navíc — ale NASA POWER číslo je z 30. 8., ne z 9. 9.

## Jak je to zapojené

`engine/datasources/nasa_power_rootzone.py` — přejmenováno z `era5_land.py`
(zavádějící jméno pro NASA data), `RootZoneReading` nese navíc
`effective_date` a `lag_days` — **explicitně**, ne skryté. API response
i UI panel (`AnalysisDetailView.tsx`) tohle zobrazují viditelně (žlutý
warning řádek), aby se zpožděná hodnota nikdy nedala zaměnit za dnešní
stav.

Pole v `RadiometricAnalyzer` výstupu přejmenována z `era5_root_zone_*`
na `power_root_zone_*` — stejný princip jako ADR-003 (samostatná pole,
NE smíchaná s relative_moisture_pct/root_zone_swi_pct), jen jiný zdroj.

## Co zůstává otevřené

- **10denní zpoždění je reálné omezení**, ne detail. Pro "co se děje
  přesně dnes" tohle pole nestačí — na to zůstává SAR (`root_zone_swi_pct`),
  co ale sám o sobě podhodnocuje (viz ADR-003). Skutečně živý A zdarma
  komerční root-zone signál pořád nemáme — kandidát je Část B z diskuze
  2026-09-09: kontinuální SWI stav napříč voláními (jen SAR, žádný nový
  externí zdroj), zatím neimplementováno.
- **~50km rozlišení NASA POWER** (MERRA-2) — hrubší než ERA5-Land (~9km).
  Pro regionální drought signál nevadí, pro přesně pole-specifické
  rozhodnutí je to hrubší aproximace než dřív.
