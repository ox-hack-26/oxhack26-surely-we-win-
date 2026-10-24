"""Manual Tiger setup/import commands. Requires explicit operator action."""
import argparse
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from clinicdrift.storage import healthcheck,init_schema,upsert_weekly,upsert_scans
from clinicdrift.mock_data import demo_weekly

load_dotenv()
p=argparse.ArgumentParser()
p.add_argument('action',choices=['healthcheck','init-schema','load-demo','import-weekly','import-scans'])
p.add_argument('--file',type=Path)
a=p.parse_args()
if a.action=='healthcheck': print('Tiger healthcheck:', 'OK' if healthcheck() else 'FAILED')
elif a.action=='init-schema': init_schema();print('Schema created/verified')
elif a.action=='load-demo': print('Imported fictional weekly records:',upsert_weekly(demo_weekly()))
else:
    if not a.file: p.error('--file is required for import')
    df=pd.read_json(a.file) if a.file.suffix.lower()=='.json' else pd.read_csv(a.file)
    print('Imported records:',upsert_weekly(df) if a.action=='import-weekly' else upsert_scans(df))
