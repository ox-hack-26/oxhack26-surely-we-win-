# Test fixtures

Alarm files frozen from the stand-in model's run (24 October 2026), so the add-on tests check the
cause-finder's logic against known numbers. The live alarms in `sample-data/alarms/` change whenever the
model or the engine does; the tests that loop over every live alarm still run against those.
