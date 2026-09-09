# ADR-003: ERA5-Land jako nezávislý zdroj kořenové zóny

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-09-09

## Kontext

I po opravách z ADR-002 (lokální baseline, medián-z-let, NDVI hradlo)
`RadiometricAnalyzer` na reálném poli (Havlíčkobrodsko, ArableLand
672112801/4) k datu 2026-09-09 vrátil `relative_moisture_pct=56.4%`,
`drought_severity=mild`. Intersucho.cz k témuž datu hlásí pro stejný
region "výjimečné až extrémní sucho". `root_zone_swi_pct=45.2%` (Wagner
SWI filtr nad SAR signálem) je blíž, ale pořád ne "extrémní".

Tohle není kalibrační chyba, co jde opravit lepší matematikou nad
stejným vstupem. Sentinel-1 C-band VV fyzicky nevidí hlouběji než ~5 cm.
Žádný filtr nad povrchovým signálem nemůže spolehlivě rekonstruovat
kořenovou zónu, kterou nikdy neměřil.

## Rozhodnutí

Přidán **nezávislý druhý zdroj** — ERA5-Land (Copernicus/ECMWF
land-surface model), co skutečně modeluje vodní bilanci ve 4 hloubkových
vrstvách (0-7, 7-28, 28-100, 100-255 cm), asimilací srážek/teploty/
radiace, ne extrapolací SAR signálu.

**Přístup:** Open-Meteo Historical Weather API
(`archive-api.open-meteo.com`), veřejné REST rozhraní BEZ nutné
registrace nebo API klíče, přímo obsluhuje ERA5-Land data. Zvažovali
jsme přímý přístup přes Copernicus Climate Data Store (CDS) API, ale ten
vyžaduje registraci a je určený spíš pro bulk NetCDF stahování než
lehké programové dotazy — Open-Meteo je stejná podkladová data, nulové
tření navíc.

## Živě ověřeno

Vrstva `soil_moisture_28_to_100cm_mean` (nejblíž Intersucho "50-100 cm"
stanicím), pole Havlíčkobrodsko, 2026-09-09:

- Dnešní hodnota: **0.185 m³/m³**
- Historie: ±21denní sezónní okno, roky 2021-2025, 215 vzorků
- Historické rozpětí: **0.245 (min) — 0.404 (max)**
- Dnešní hodnota je **pod minimem celé 5leté historie** — ne "nízký
  percentil", nejsušší den v datové řadě pro tohle období

Tohle se řádově líp shoduje s Intersucho "extrémní sucho" než SAR-odvozené
signály. Nejde o vybranou shodu na jednom čísle — je to nezávislé
potvrzení stejným směrem, jiným zdrojem, jinou fyzikou.

## Jak je to zapojené — a jak NE

`RadiometricAnalyzer.analyze()` přijímá volitelný `era5_reading`
parametr. Výsledek se zapisuje jako **samostatná pole**
(`era5_root_zone_vwc`, `era5_root_zone_percentile_rank`,
`era5_below_historical_range`, `era5_depth_layer`) — **NE smíchaný**
do `relative_moisture_pct` ani `root_zone_swi_pct`.

**Proč ne fúze do jednoho čísla:** dva nezávislé zdroje s různou fyzikou
(10 m SAR vs. ~9 km reanalýza modelu) a různým rozlišením se nemají tiše
zprůměrovat — to by schovalo jejich nesouhlas, ne ho ukázalo. Když SAR
říká "mild" a ERA5-Land říká "pod historickým minimem", uživatel má
vidět OBOJÍ a vědět, kterému věřit pro jakou hloubku — ne dostat jedno
kompromisní číslo, co je matoucí pro obě otázky.

`measurement_caveat` teď explicitně říká: SAR signály jsou pro
povrchovou vrstvu, `era5_root_zone_percentile_rank` je nezávislý
hloubkový odhad, a při rozporu věřit spíš jemu pro hloubku.

## Co zůstává otevřené

- **Jedno pole, jedno datum jako důkaz.** Stejné pravidlo jako u ADR-002
  — potřeba víc polí a časových bodů, než se dá tvrdit, že ERA5-Land
  systematicky sedí líp, ne jen že sedělo tentokrát.
- **~9 km rozlišení ERA5-Land** vs. 10 m SAR — pro malé pole (pár ha)
  reanalýza fakticky popisuje širší okolí, ne přesně to pole. Pro
  regionální drought monitoring to nevadí, pro přesné pole-specifické
  rozhodnutí je to aproximace.
- **Žádná skutečná fúze zatím** — dva čísla vedle sebe, ne jeden
  kalibrovaný odhad, co by kombinoval sílu obou (vysoké rozlišení SAR +
  fyzikálně správnou hloubku ERA5-Land). To je logický další krok, ne
  triviální — vyžaduje validaci, ne jen vzorec.
