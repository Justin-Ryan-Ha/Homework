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

By default, PNG charts are saved in an `eld_charts` folder beside the input
CSV. To choose another folder, pass `--output-dir`:

```bash
python "FMCSA Log Generator.py" path/to/eld_file.csv --charts --output-dir path/to/output
```

The chart plots active duty-status changes on a 24-hour grid. It is a daily
graph, not a complete roadside ELD report.
