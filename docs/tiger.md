# Tiger Data: storing and serving ClinicDrift's monitoring data

ClinicDrift writes every scan its simulated clinics take, the model's output for each, and the engine's weekly monitoring results to Tiger Data (TimescaleDB). The dashboard reads them back with time-bucketed queries. Code: `db/migrations/` (schema), `clinicdrift/db/tiger.py` (migrate, ingest, demo commands), `dashboard/ui/tiger.py` (the dashboard's read-only queries), `tests/test_tiger.py`.

## Setup

1. **Create a service.** In Tiger Cloud, create a service with the default TimescaleDB setup ([quick start](https://www.tigerdata.com/docs/get-started/quickstart/create-service)) and download its config file when offered. That download is the only time the console shows the password. The connection string looks like `postgres://tsdbadmin:<PASSWORD>@<HOST>:<PORT>/tsdb?sslmode=require`; without the password, the details are also under the service's *Connect* panel ([docs](https://www.tigerdata.com/docs/integrate/find-connection-details)).
2. **Set it locally**, in the repo's `.env` (never committed), on one line:

   ```
   TIGER_DATABASE_URL=postgres://tsdbadmin:<PASSWORD>@<HOST>:<PORT>/tsdb?sslmode=require
   ```

   The code also accepts `TIMESCALE_SERVICE_URL` or `DATABASE_URL`, and never prints the URL or the password, even in connection errors. Use the service's direct connection string; the pooled one (database `tsdb_transaction`) also works, because nothing is set on the session and the dashboard's read-only mode is per transaction.
3. `pip install -r requirements.txt` (includes `psycopg[binary]`).

No service yet? A local TimescaleDB works the same:

```bash
docker run -d --name clinicdrift-tsdb -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=<choose one> -e POSTGRES_DB=tsdb timescale/timescaledb:2.31.0-pg17
```

and `TIGER_DATABASE_URL=postgres://postgres:<that password>@127.0.0.1:55432/tsdb`.

## Commands

| What | Command |
| --- | --- |
| Create or update the tables (safe to repeat) | `python -m clinicdrift.db.tiger migrate` |
| Store the shared sample data (what the team's dashboard shows) | `python -m clinicdrift.db.tiger ingest --data sample-data` |
| Store the engine's latest run (`processed/`) | `python -m clinicdrift.db.tiger ingest` |
| Run the whole engine, then store its results | `python -m clinicdrift.engine.pipeline --tiger` |
| Turn on the columnstore and measure the real compression | `python -m clinicdrift.db.tiger compress` |
| Row counts, latest ingest, compressed chunks | `python -m clinicdrift.db.tiger check` |
| Add one live demo scan to a clinic-week | `python -m clinicdrift.db.tiger demo-event --clinic US-WEAR-01 --week 9` |
| Remove the demo scans | `python -m clinicdrift.db.tiger clear-demo` |
| Dashboard on Tiger | in `dashboard/.env` set `CLINICDRIFT_DATA_MODE=tiger`, then from `dashboard/`: `python -m streamlit run app.py` |
| Tests (live ones need a database) | `python -m pytest -q tests/test_tiger.py`, with `TIGER_TEST_DATABASE_URL=...` for the live ones |

`ingest` runs `migrate` first. Ingesting the same folder again writes no duplicates: every table is upserted on its primary key, and rows of the same model that the folder no longer contains (a changed replay) are removed. Each model gets its own `model_version` (its architecture plus a hash of `model.json`), so the stand-in's and the real model's scores for the same scans can sit side by side; the dashboard shows the most recently ingested one.

## What is stored

| Table | What | Tiger feature |
| --- | --- | --- |
| `scan_events` | One row per scan a clinic took: event time `ts`, clinic, model version, model score `p_referable`, the cut-off in force, referred or not, image quality, camera wear, and the expert grade with `graded_at` for the ~10% of scans an expert checks | Hypertable on `ts` (weekly chunks), primary key `(scan_id, model_version, ts)`; columnstore with `segmentby clinic_id, model_version` |
| `scan_stats_daily` | Per clinic, model and day: scans, sum of scores, referrals, quality, wear, scans awaiting grades, demo events | Continuous aggregate, real-time (`materialized_only = false`), refresh policy every 5 minutes plus an explicit refresh after each ingest |
| `weekly_monitoring` | The engine's weekly output: estimated and believed catch rate with band, drift, expected harm, alarm (columns as in `docs/handoffs.md`; new engine columns go into `extra`) | Hypertable on `week_start` |
| `alarms` | The alarm files the add-ons read, kept whole | JSONB |
| `clinics`, `model_versions`, `ingest_runs` | Clinic list; each model's threshold and validation scores; one row per ingest with the replay fingerprint and decision settings | |

Times: `ts` and `week_start` are **event times** from the replay (simulated scans, January–May 2026); `ingested_at` is when the row was written. `data_origin` marks every scan row as `simulated_replay` or `demo_live`. Images and model weights stay where they are (the data folder); only scores and metadata go to Tiger.

The dashboard's Tiger panel rolls the daily aggregate up with `time_bucket('7 days' | '1 day')` for the selected clinic and weeks, and recomputes from the raw hypertable how many expert grades had arrived by the end of the selected week and how many of those urgent cases the AI caught. That is the only place it calculates a catch rate from ground truth, because only graded scans have one, and it checks the result against the engine's own count.

## Two-minute sponsor demo

1. `python -m clinicdrift.db.tiger check`: 9,500 scan events per model in weekly chunks, 200 clinic-weeks, compressed.
2. Dashboard in Tiger mode, clinic **US-WEAR-01**, week 9: the banner shows it is reading Tiger (model, ingest run, replay fingerprint). The *Stored in Tiger Data* panel shows 50 scans a week from the continuous aggregate, and the expert grades that had arrived by week 9 straight from the hypertable, matching the engine.
3. `python -m clinicdrift.db.tiger demo-event --clinic US-WEAR-01 --week 9`, then refresh the page: week 9 now has 51 scans and the panel counts one live demo event. Real-time aggregation makes it visible at once; the command also refreshes the aggregate.
4. `python -m clinicdrift.db.tiger compress`: the real before/after size of the scan hypertable.
5. `python -m clinicdrift.db.tiger clear-demo`.

Pitch line: *ClinicDrift streams every screening scan into a Tiger hypertable; a real-time continuous aggregate gives each clinic's weekly volume and model scores the moment a scan lands, while the slow expert grades join the same table weeks later, so one SQL query answers "what had the experts confirmed by this date?" without leaking the future.*

## Verified so far

| Check | Local TimescaleDB 2.31.0 (Docker) | Tiger Cloud |
| --- | --- | --- |
| Migration runs twice without changes | yes | not yet: needs the service URL |
| Small batch ingested; repeating it adds no duplicates | yes (tests) | not yet |
| Full sample-data and real-model runs ingested, then re-ingested with 0 inserted / 9,500 updated | yes | not yet |
| Clinic and time-range queries return the replay's counts | yes (tests) | not yet |
| Dashboard reads weekly results, clinics, settings and the Tiger panel, and cannot write | yes (tests and a browser check) | not yet |
| Connection errors never show the password; stand-in engine runs ingest from `processed/standin/` | yes (tests) | not yet |
| Demo event appears after refresh; clear-demo removes it | yes | not yet |
| Columnstore: 21 of 21 chunks converted, scan_events 14.9 MB to 4.5 MB (3.3x) | yes | not yet |

Run the same commands against Tiger Cloud once `TIGER_DATABASE_URL` is set, and update this table before quoting it.
