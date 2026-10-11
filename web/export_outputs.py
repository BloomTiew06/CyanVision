"""Copy the forecast files the app needs from a pipeline output folder into web/outputs/ for the browser build.

    python web/export_outputs.py outputs          # after a real-data pipeline run
    python web/export_outputs.py outputs_mock     # sample data

The browser runtime can't read Parquet, so forecasts.parquet is written as a gzipped CSV (app.py reads either).
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

src = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs")
dst = Path(__file__).parent / "outputs"
if not (src / "metrics.json").exists():
    sys.exit(f"{src} has no metrics.json. Run pipeline.py first.")
dst.mkdir(exist_ok=True)
pd.read_parquet(src / "forecasts.parquet").to_csv(dst / "forecasts.csv.gz", index=False)
for name in ("metrics.json", "sigma.csv", "uncertainty.csv"):
    if (src / name).exists():
        shutil.copy(src / name, dst / name)
print(f"Wrote {', '.join(sorted(p.name for p in dst.iterdir()))} to {dst}")
