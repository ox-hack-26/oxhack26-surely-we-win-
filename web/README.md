# Dashboard (Sneha)

Reads weekly results from Tiger Data (`db/schema.sql`) or straight from `processed/weekly.parquet` (see `docs/handoffs.md`). Until the engine produces real files, build against fake rows with the same columns.

Screens: clinic list, estimate-versus-real chart with the uncertainty band, alarm, replay slider, cost sliders.
