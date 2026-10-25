# ClinicDrift dashboard: Tejas handoff integration

Run from the repository root:

```bash
cd dashboard
../.venv/bin/python -m streamlit run app.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest -q tests/
```

The dashboard reads `../sample-data/weekly.csv`, `clinics.json`, `decision_settings.json`, and `alarms/` by default. You can override with `CLINICDRIFT_SAMPLE_DATA`.

**Key points:** `catch_rate` with `catch_low`/`catch_high` is the main belief. `est_sensitivity` is the naive baseline. `true_sensitivity` is hidden by default because it uses full hindsight. Already-arrived expert evidence is represented by `graded_cases` and `graded_caught`.

The cost sliders use the formula in `docs/handoffs.md`, with reference specificity/prevalence from `decision_settings.json`. The original latched alarm is unchanged by sliders; slider decisions are exploratory. All clinical data is simulated.

`dashboard/ui/` replaces `dashboard/clinicdrift/` to avoid shadowing the engine's root `clinicdrift` package.

## Tiger Data

With `CLINICDRIFT_DATA_MODE=tiger` the dashboard reads its weekly results, clinics, settings and alarms from Tiger Data and shows a *Stored in Tiger Data* panel (`ui/tiger.py`); the default is the offline `sample-data/` files, labelled as such. The schema that runs is `db/migrations/`; setup, commands and what has been verified are in [docs/tiger.md](../docs/tiger.md). `sql/tiger_prize.sql` is the earlier review-only draft.

The old `sql/schema.sql` and `ui/storage.py` are retained for backward compatibility with earlier prototype tests, not as the new handoff schema.

## Merge safely

This ZIP is a patch source, not a full Git repository. Copy only `dashboard/` changes into the existing team repo. Do not replace root `clinicdrift/`, `sample-data/` or `docs/`. Review `git diff` and run tests before pushing `dev`.

### Database operations (not performed)

After verifying your service's TimescaleDB extension and that `clinicdrift_demo` does not collide with any existing objects, review `sql/tiger_prize.sql`. The optional columnstore plan is in `sql/tiger_columnstore_optional.sql` and intentionally contains no executable ALTER/policy statements. It is not proof of a compression benchmark. Before claiming the Tiger prize features, ingest scan events, refresh the aggregate, verify query outputs, and collect real compression statistics.
