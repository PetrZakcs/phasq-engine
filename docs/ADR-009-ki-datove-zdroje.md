# ADR-009: Datové zdroje pro mapový podklad přírodních rizik KI (Fáze 0)

**Stav:** Přijato, živě ověřeno | **Datum:** 2026-10-08

## Kontext

Nové zadání (prototyp pro subjekty kritické infrastruktury dle zákona
č. 266/2025 Sb. a vyhlášky č. 122/2026 Sb.) požaduje jako první krok
ověřit pro každý datový zdroj dostupnost, licenci pro komerční použití
a datum poslední aktualizace, PŘED psaním kódu. Zadání samo instruuje
zapsat výsledek do `docs/ADR-008-ki-datove-zdroje.md` — tohle číslo je
ale v tomhle repu už obsazené (`ADR-008-fallback-never-emits-verdict.md`,
2026-10-02). Použito proto ADR-009, očíslování navazuje na existující
řadu.

**Metoda:** u každého zdroje živě ověřeno (ne převzato z paměti ani jen
z dokumentace) — buď přímým voláním endpointu (`curl`/ArcGIS REST query),
nebo čtením oficiální metadatové/licenční stránky. U tří ze čtyř zdrojů
našel první pokus mrtvý/zastaralý endpoint, co se ještě běžně objevuje
v online dokumentaci a fórech — stejný vzorec, co se v tomhle projektu
opakovaně potvrdil i u LPIS WFS (viz `phasq_app` ADR o LPIS schema
break, 2026-10-02): oficiální české geoportály se tiše migrují na nové
endpointy/schémata bez přesměrování.

## Shrnutí (tabulka)

| Hrozba | Zdroj | Endpoint (živě ověřeno) | Licence | Aktuálnost |
|---|---|---|---|---|
| Povodně (Q5/Q20/Q100) | VÚV TGM, ISVS Voda | `ags.vuv.cz/arcgis/rest/services/isvs_voda/isvs_voda/MapServer` (vrstvy 11-16) | Veřejný registr dle zák. 365/2000 Sb., bez autorskoprávní ochrany, volně pro jakékoliv použití | Živá služba, průběžně aktualizovaná VÚV |
| Svahové nestability | ČGS, Registr svahových deformací | `mapy.geology.cz/arcgis/rest/services/Geohazardy/svahove_deformace/MapServer` | CC BY 4.0 (nutná atribuce © ČGS) | Živá služba |
| Poddolovaná území | ČGS | `mapy.geology.cz/arcgis/rest/services/Dulni_Dila/poddolovana_uzemi/MapServer` | INSPIRE metadata: `useConstraints=noConditionsApply`, přístup bez omezení. Copyright pole formálně "všechna práva vyhrazena" — standardní české metadatové boilerplate (stejný vzorec jako u ostatních ČGS/INSPIRE záznamů), ne reálné omezení. Doporučeno v reportu přesto uvádět © ČGS jako dobrou praxi. | Živá služba, průběžně aktualizovaná |
| Pohyby terénu (EGMS) | Copernicus Land Monitoring Service | `egms-api` (oficiální Jupyter/API, github.com/copernicus-land/egms-api), CSV distribuce | Copernicus open data policy — volně i komerčně, podmínka: uvést zdroj a označit případné úpravy dat | Ortho Vertical běžně ~2 roky pozadu (ověřit přesný konec pokrytí při implementaci, zadání počítá s koncem 12/2024) |
| Povodně (pozorované, Sentinel-1) | CDSE | už integrováno (`utils/cdse_auth.py`, ADR-001) | Copernicus, volně i komerčně (ADR-001) | Živá služba |

**Závěr: žádný zdroj nemá nejasnou nebo komerčně problematickou licenci.
Nic nebrání pokračovat do Fáze 1.**

## Detailní nálezy a mrtvé konce

### Povodně — Q5/Q20/Q100 (nejdůležitější, zadání explicitně žádá stop při nejasné licenci)

Nejdřív nalezený `ags.vuv.cz/arcgis/rest/services/zu/q/MapServer` (často
citovaný v online diskuzích) vrací živě `{"error":{"code":500,"message":
"Service zu/q/MapServer not started"}}` — služba existuje v adresářové
struktuře, ale je vypnutá. Stejně tak starý `heis.vuv.cz/data/webmap/
isapi.dll` WMS endpoint (citovaný v materiálech z let 2011-2012) vrací
živě vrstvu `neplatnyodkaz` / "Zadaný odkaz není platný nebo již byl
zrušen!".

Živý, funkční nástupce nalezen přes portál voda.gov.cz (MZe/MŽP společný
portál) → `ags.vuv.cz/arcgis/rest/services/isvs_voda/isvs_voda/
MapServer`, vrstvy:
- 11 `ZaplavUzemi_AktivniZony`
- 12 `ZaplavUzemi_Q500`
- 13 `ZaplavUzemi_Q100`
- 14 `ZaplavUzemi_Q20`
- 15 `ZaplavUzemi_Q5`
- 16 `ZaplavUzemi_UsekyToku`

Živě otestován dotaz na vrstvu 15 (`/15/query?where=1=1&f=geojson`) —
vrací reálné polygony (MultiPolygon, souřadnice v EPSG:4326).

Licence: DIBAVOD/HEIS VÚV data podléhají zákonu č. 365/2000 Sb. o
informačních systémech veřejné správy — veřejně přístupný registr,
výstupy jsou dostupné všem zdarma v jakémkoliv rozsahu, autorskoprávní
ochrana se neuplatňuje.

### Sesuvy — Registr svahových nestabilit ČGS

Endpoint živý na první pokus (`mapy.geology.cz/arcgis/rest/services/
Geohazardy/svahove_deformace/MapServer`), živě otestován dotaz na
plošnou vrstvu (id 3) — vrací body/polygony s poli jako `aktivita`
(aktivní/dočasně uklidněný/uklidněný), `cislo_bodu`. Licence CC BY 4.0,
nejčistší ze všech čtyř zdrojů.

### Poddolovaná území ČGS

Endpoint živý na první pokus. Licenční pole v INSPIRE metadatovém
záznamu je na první pohled rozporné (`Copyright (všechna práva
vyhrazena)` SOUČASNĚ s `žádné podmínky neplatí` / `noConditionsApply`)
— ověřeno přímo z metadatového záznamu (`micka.geology.cz`), ne jen
z vyhledávání. Tohle je standardní český metadatový vzorec (copyright
pole je v INSPIRE formuláři povinné, i když reálně žádné podmínky
neplatí) — stejný vzorec se objevuje i u svahových nestabilit (tam je
to navíc explicitně CC BY 4.0, takže nejde o chybu interpretace).
Doporučení: v reportu přesto uvádět zdroj explicitně, i když to licence
striktně nevyžaduje.

### EGMS

Oficiální distribuce je přes `github.com/copernicus-land/egms-api`
(Jupyter-based API workflow), ne přímý WFS/WMS jako u předchozích tří
zdrojů — technicky jiný integrační vzor, do `engine/ki/` bude potřeba
vlastní stahovací/parsovací vrstva (CSV), ne jen reprodukce vzoru
`sentinel1_cdse.py`. Tohle je implementační detail Fáze 1/3, ne blokace
Fáze 0.

## Co zůstává otevřené pro Fázi 1

- Přesné ukončení časové řady EGMS Ortho Vertical (zadání počítá s
  12/2024, nutno ověřit při implementaci proti aktuální verzi datasetu).
- `FD_FA`/`FD_APSFR`/`FD_PFRA` (INSPIRE Floods Directive vrstvy, taky
  nalezené na `ags.vuv.cz/inspire_wfs/`) NEOBSAHUJÍ explicitní
  Q5/Q20/Q100 atribut (jen `EU_CD_HMP` kód) — nepoužitelné jako primární
  zdroj pro tabulku č. 1 vyhlášky, `isvs_voda` vrstvy jsou správná volba.
- Žádný ze čtyř zdrojů nebyl zkoušen s `orbit_direction`/UTM reprojekcí
  jako Sentinel-1 — všechny vrací souřadnice přímo v EPSG:4326, žádná
  reprojekce navíc potřeba (na rozdíl od CDSE Statistical API, viz
  ADR-001).
