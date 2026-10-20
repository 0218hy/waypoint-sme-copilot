# Public data sources

Everything in `areas.json`, `planning_areas.geojson` and `stations.json` comes from the public
datasets below. No value is invented or estimated. A field without a real, machine-readable source
is `null` (or `{}`), and the gap is listed at the end of this file. `simulated_fields` is empty for
every area.

- Retrieved: 2026-10-19 (raw files in `raw/`, gitignored; SHA-256 of every raw file and output in
  `checksums.txt`)
- Rebuild: `python -m data.public.fetch` (download, cached in `raw/`, then process);
  `python -m data.public.fetch --offline` (reprocess `raw/` without network);
  `--refresh` re-downloads everything.
- data.gov.sg licence: [Singapore Open Data Licence v1.0](https://data.gov.sg/open-data-licence).
  SingStat website datasets are also under the Singapore Open Data Licence, per the
  [SingStat Terms of Use](https://www.singstat.gov.sg/terms-of-use).
  OneMap search API: [OneMap terms of use](https://www.onemap.gov.sg/legal/termsofuse.html)
  (Singapore Land Authority).

## Field → source

| Field | Dataset | Publisher | Dataset id | URL | As of | Licence |
|---|---|---|---|---|---|---|
| `id`, `name`, `region`, geometry, `centroid` | Master Plan 2019 Planning Area Boundary (No Sea) | Urban Redevelopment Authority | `d_4765db0e87b9c86336792efe8a1f7a66` | https://data.gov.sg/datasets/d_4765db0e87b9c86336792efe8a1f7a66/view | MP2019 (coverage from 2019-12-23; file updated 2025-12-05) | SODL v1.0 |
| `residents`, `age_shares` | Singapore Residents by Planning Area / Subzone, Age Group, Sex and Type of Dwelling, June 2026 | Singapore Department of Statistics | `singstat:respopagesextod` (file `respopagesextod2026.csv`) | https://www.singstat.gov.sg/find-data/explore-data-themes/population/geographic-distribution/latest-news-data (file https://www.singstat.gov.sg/files/c6755f50-4bfb-4bfa-b7d3-00259b9509ed.zip) | June 2026 (generated 2026-09-25) | SODL v1.0 (via SingStat Terms of Use) |
| `income_shares` | Resident Households by Planning Area of Residence and Monthly Household Income from Work (Census of Population 2020) | Singapore Department of Statistics | `d_4e150bbd35c3145ea43019212c7b46c2` | https://data.gov.sg/datasets/d_4e150bbd35c3145ea43019212c7b46c2/view | Census 2020 (revised 2026-06-30 to include Additional MediSave Contributions) | SODL v1.0 |
| `daytime_proxy` | Employed Residents Aged 15 Years and Over by Planning Area of Workplace, Age Group and Sex (Census of Population 2020) | Singapore Department of Statistics | `d_22063c84778e6535b92b4d8f93fd2525` | https://data.gov.sg/datasets/d_22063c84778e6535b92b4d8f93fd2525/view | Census 2020 | SODL v1.0 |
| `food_outlets` | List of NEA Licensed Eating Establishments | National Environment Agency | `d_227473e811b09731e64725f140b77697` | https://data.gov.sg/datasets/d_227473e811b09731e64725f140b77697/view | coverage 2015-06-11 to 2016-09-06 | SODL v1.0 |
| `food_outlets` (geocoding) | OneMap Search API (postal code or block + road → lat/lng) | Singapore Land Authority | — | https://www.onemap.gov.sg/apidocs/search | retrieved 2026-10-19 | OneMap terms of use |
| `stations.json` (station points, per-area lists) | LTA MRT Station Exit (GEOJSON) | Land Transport Authority | `d_b39d3a0871985372d7e1637193335da5` | https://data.gov.sg/datasets/d_b39d3a0871985372d7e1637193335da5/view | file updated 2026-10-18 | SODL v1.0 |
| `stations.json` (`codes`) | Train Station Chinese Names | Land Transport Authority | `d_d312a5b127e1ae74299b8ae664cedd4e` | https://data.gov.sg/datasets/d_d312a5b127e1ae74299b8ae664cedd4e/view | coverage 2017-06-27 (updated 2024-06-06) | SODL v1.0 |
| `station_traffic_monthly` | Passenger Volume by Train Stations (`PV/Train`) | LTA DataMall | — | https://datamall.lta.gov.sg/content/datamall/en/dynamic-data.html | **not fetched** (needs `LTA_ACCOUNT_KEY`) | LTA DataMall terms |
| `rent_psf_month_sgd` | — | — | — | — | **no machine-readable source found** | — |

Each entry's `sources` map in `areas.json` repeats the dataset id, title and as-of date per field.

## How each field is derived

- **Boundaries** (`planning_areas.geojson`): all 55 MP2019 planning areas are kept (the dataset
  marks none as sea or uninhabited). Properties are `{id, name, region}`: `id` is `PLN_AREA_N`
  exactly as published (e.g. `JURONG EAST`), `name` is its Title Case, `region` is the Title Case
  of `REGION_N`. Geometry is WGS84 as published, simplified with Douglas–Peucker (tolerance
  1e-5 degrees, about 1 m) and rounded to 5 decimal places. Rings that collapse to fewer than three
  distinct points at 5 dp (sub-metre slivers: 1 in Jurong East, 4 in Southern Islands, 1 in
  Western Islands) are dropped. Point-in-polygon counts use the unsimplified geometry.
- **`centroid`**: area-weighted planar centroid of each area's polygons (holes subtracted), as
  `[lat, lng]`.
- **`residents`**: sum of `Pop` over every subzone, age group, sex and dwelling type for the
  planning area. SingStat rounds each cell to the nearest 10, so totals carry rounding noise.
  Areas with 0 are published as 0 (e.g. Changi Bay, Tuas).
- **`age_shares`**: `0-19` = 0–4 … 15–19; `20-39` = 20–24 … 35–39; `40-59` = 40–44 … 55–59;
  `60+` = 60–64 … 90 and over. Share of the area's residents, 4 dp. Empty `{}` when the area has
  0 residents.
- **`income_shares`** (share of resident households, 4 dp; denominator is the sum of the bins, which
  differs from the published total by at most 3 households because of SingStat's rounding):

  | Band | Census bins |
  |---|---|
  | `<4k` | No employed person, below $1,000, $1,000–1,999, $2,000–2,999, $3,000–3,999 |
  | `4k-8k` | $4,000–4,999 … $7,000–7,999 |
  | `8k-12k` | $8,000–8,999 … $11,000–11,999 |
  | `12k+` | $12,000–12,999 … $17,500–19,999, $20,000 and over |

  Income is household income **from work** including employer CPF; households with no employed
  person (often retirees) are in `<4k`. Census 2020 publishes this table for 30 planning areas
  only; the rest are pooled as "Others" and are left `{}` (not apportioned).
- **`daytime_proxy`**: employed residents (citizens and PRs) whose usual workplace is in the
  planning area, divided by the largest such count (Downtown Core = 1.0). Census 2020 publishes
  it for 44 planning areas; the rest are pooled as "Other Planning Areas or Outside Singapore" and
  are left `null`. It excludes non-resident workers and students, so it under-counts daytime
  population in areas with many foreign workers.
- **`food_outlets`**: each row of the NEA list is one licensed eating establishment (restaurants,
  coffee-shop and food-court stalls, canteens and hawker/market stalls). Rows are located with
  OneMap search, accepting only strict matches (no fuzzy matches):
  - rows with a 6-digit postal code at the end of `premises_address`: the OneMap hit whose
    `POSTAL` equals that code (29,823 rows);
  - hawker/market stall rows, which have no postal code (e.g. `BEDOK NORTH ST 4 BLK 85 Stall No
    01-21`): the hit whose `BLK_NO` equals the block and whose `ROAD_NAME` has the same words after
    expanding abbreviations (ST → STREET, LOR → LORONG, AVE → AVENUE, …; word order ignored), or,
    for named centres (e.g. `AMOY STREET FOOD CENTRE`), the hit whose building name equals the
    name (5,563 rows; the accepted OneMap address for each is kept in
    `raw/onemap_stall_geocode.json`).

  Each point is assigned to a planning area by point-in-polygon. Of 36,687 rows, 35,386 are
  counted; 1,297 have no strict OneMap match (784 rows whose postal code has no exact OneMap match, plus
  construction-site canteens, land-lot descriptions and a few stall centres such as Taman Jurong
  Market & Food Centre and Commonwealth Drive) and 4 fall outside every planning area. Unmatched
  rows are not counted, so counts are slight under-counts.
- **`stations.json`**: station exits are grouped by `STATION_NA` (e.g. `TAMPINES MRT STATION`);
  the station point is the mean of its exits, and the station is assigned to the planning area
  containing that point. MRT and LRT stations with the same name (e.g. Punggol MRT and Punggol
  LRT) are listed separately, as in the dataset. `codes` comes from the Train Station Chinese
  Names table, joined by English name; stations opened after that table (TEL and some others) have
  no codes. The per-area station count is the length of each list.
- **`station_traffic_monthly`** (only when `LTA_ACCOUNT_KEY` is set): sum of `TOTAL_TAP_IN_VOLUME`
  and `TOTAL_TAP_OUT_VOLUME` for the latest `YEAR_MONTH` over every station inside the area,
  matched by `PT_CODE` to the station codes above.

## Gaps (fields left null and why)

| Field | Status | Reason |
|---|---|---|
| `station_traffic_monthly` | null for all 55 areas | LTA DataMall `PV/Train` requires an AccountKey and none was set (`LTA_ACCOUNT_KEY`). `fetch.py` downloads and processes it when the key is provided. DataMall serves only the last three months. Stations without codes (TEL and others missing from the 2017 code table) would not be matched. |
| `rent_psf_month_sgd` | null for all 55 areas | URA publishes median retail rents ($ psf pm, by Central Area/Orchard vs outside) only in PDF annexes to its quarterly releases. The data.gov.sg dataset "Median Rentals and Vacancy of Retail Space by Locality" (`d_49962204d37550d54175c2e5f0e78025`) has been unpublished (API returns `DATASET_DOES_NOT_EXIST`). The only machine-readable retail rent series on data.gov.sg is an index (Property Rental Index, Retail in Central Region, `d_a6c0ffc105817820388fd7b46fc67b13`), which has no $ psf level. URA's Data Service API needs an access key. Unit rents come from the (simulated) unit listings. |
| `income_shares` | `{}` for 25 areas | Census 2020 pools them as "Others" (see above). |
| `daytime_proxy` | null for 11 areas | Census 2020 pools them as "Other Planning Areas or Outside Singapore". |
| `age_shares` | `{}` for 13 areas | 0 residents in June 2026, so no shares. |
| `food_outlets` freshness | 2015–2016 snapshot | The NEA list is the only food-establishment dataset with premises addresses on data.gov.sg. The SFA "Eating Establishments" location layer is no longer listed on data.gov.sg, and SingStat's "Licensed Food Establishments" is a national total only. Counts reflect 2015–2016, not today. |
| Population vintage | mixed | Residents and ages are June 2026, which SingStat demarcates by the **Master Plan 2025** planning areas. Income and workplace are Census 2020 (MP2019). The boundaries are MP2019 as specified. MP2025 has the same 55 planning-area names and regions; areas differ by under 1.1% except Changi (+4.6%) and Changi Bay (reclamation, 0 residents). |
