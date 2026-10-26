# FMCSA Log Generator

This Python project reads FMCSA-structured electronic logging device (ELD) data
from a CSV file, parses its sections and events, and can produce a 24-hour daily
duty-status chart using Matplotlib.

## Install

```bash
python -m pip install -r requirements.txt
```

## Generate daily charts

```bash
python "FMCSA Log Generator.py" path/to/eld_file.csv --charts
```

If you want to use a short filename instead of a full path, place the CSV in
the same folder where you run the command. For example, if the CSV is named
`driver_logs.csv` and is in the project folder, run:

```bash
python "FMCSA Log Generator.py" driver_logs.csv --charts
```

You can also provide a relative or absolute path to a CSV stored elsewhere.

By default, PNG charts are saved in an `eld_charts` folder beside the input
CSV. To choose another folder, pass `--output-dir`:

```bash
python "FMCSA Log Generator.py" path/to/eld_file.csv --charts --output-dir path/to/output
```

Each day's chart includes a timestamp-ordered table with one row per event
record, including duty-status and intermediate events, login/logout activity,
unidentified-driver records, certifications, engine activity, and malfunctions
or diagnostics. The graph plots active duty-status changes on a 24-hour grid.
This is a daily graph and event ledger, not a complete roadside ELD report.
