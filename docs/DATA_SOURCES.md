# Data sources

RailOpt AI uses two kinds of data, which are never mixed:

| Label | What | Where |
|---|---|---|
| **SIMULATED** | Reference corridor A-B-C-D, 12-train full day, generated scenarios, evaluation | `backend/data/*.csv`, `backend/data/generated/`, `backend/eval/` |
| **REAL** | Dindigul (DG) -> Madurai (MDU) corridor, Sept 2024 timetable and recorded running times | `backend/data/real/` |

Every REAL file and output carries `data_label = REAL`. Decisions computed on top of a real
recording (Step 3, later) are labelled "HYPOTHETICAL on a real recorded day".

## REAL: running data and timetable

**RSTGCN dataset: "Indian Railway Operations and Delay Dataset - September 2024"**

- Authors: Koyena Chowdhury, Paramita Koley, Abhijnan Chakraborty, Saptarshi Ghosh (IIT Kharagpur, IIIT Bhubaneswar).
- Paper: "RSTGCN: Railway-centric Spatio-Temporal Graph Convolutional Network for Train Delay
  Prediction", arXiv:2510.01262 (v1 26 Sep 2025, v2 22 Aug 2026), to appear in IEEE T-ITS
  (doi:10.1109/TITS.2026.3726308). The paper says the dataset is available for research purposes.
- Download: https://github.com/KoyenaChowdhury/RSTGCN, file `Indian-Railway-Network-and-Delays.zip`
  (24,041,934 bytes, sha256 `f8a6fe9e70972acb8ad98bbe5b7eb594c5b6b3475e21efd6d3b9e19049bdaf91`).
  Downloaded 2026-11-15 to `backend/data/real/raw/` (gitignored).
- Licence: **CC BY-SA 4.0**, as stated on the DataHub KGP listing
  (https://datahubkgp.org/datasets/79deb8a0a7d361bb4f27). The GitHub repository has no LICENSE file.
  Checked 2026-11-15. The committed corridor extract is shared under the same licence: see
  `backend/data/real/LICENSE-DATA`.
- How the data was collected: by the dataset authors from https://runningstatus.in/, a
  third-party running-status website (not NTES). RailOpt AI did not scrape NTES, IRCTC or any website.
- Coverage: about 3,892 long-distance passenger trains, journey start dates 1-30 Sept 2024. Freight
  and local (passenger/MEMU) trains are excluded by the authors.
- Files used: `train_routes_Sep2024.csv` (scheduled route and times, the primary timetable) and
  `train_routes_delays_Sep2024.csv` (scheduled and actual arrival/departure per train, date, station).

Per-train source and date checked are in `backend/data/real/dg_mdu/trains.csv`
(`timetable_source`, `source`, `date_checked`). Per-cell provenance is in `schedule.csv`
(`time_source`: DATASET_ROUTE, DATASET_RECORDS or ESTIMATED).

## REAL: corridor geometry

- **Station chainages ABI..MDU**: Southern Railway Madurai division system map 2024
  (`SR MDU Divn Map 2024.pdf`, indianrailways.gov.in, Railway Board civil engineering system maps),
  values supplied by the project owner. On 2026-11-15 the PDF URL returned HTTP 404 ("Site Under
  Construction") from here, so the values could not be re-read.
- **DG chainage**: not readable (the 2024 map and the 2021 SR zonal map both returned 404 on
  2026-11-15). **DERIVED** = ABI 444.02 - 11 km (DG-ABI in the dataset's route file) = 433.02 km.
  See ASSUMPTIONS.md 48 for the 1-4 km disagreement between dataset distances and the map.
- **Tracks**: one track per direction (owner-supplied: "twin single line").
- **Platforms, minimum headway, minimum running times**: not public, **ASSUMED** (ASSUMPTIONS.md 49-51).

## Not used

- NTES, IRCTC and other live-status or booking websites: not scraped, not used.
- Freight paths: not public; freight appears only in SIMULATED scenarios.

## Regenerate

From `backend/` (needs the raw zip):

```
python -m app.services.realdata.extract
python -m app.services.realdata.audit
```

`tests/test_realdata.py` checks the extract reproduces byte-for-byte from the zip (skipped
without it) and that `audit.md` matches `audit.json`.
