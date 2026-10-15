# wifi-site-survey

Walk a site with a laptop, log every access point you can hear, and generate a
shareable HTML site-survey report — coverage by location, weak-spot flagging,
and channel congestion analysis.

Built for field technicians doing Wi-Fi surveys, troubleshooting dead zones,
and documenting wireless deployments for clients. Zero dependencies, works on
Windows, Linux, and macOS.

## Quick start

```bash
# One-shot scan (prints a table, logs to survey.csv)
python wifi_survey.py scan

# Log one SSID continuously while you walk the site
python wifi_survey.py watch --location "Warehouse Aisle 3" --interval 10 --duration 5

# Guided walkthrough: step through a location list, one scan per spot
python wifi_survey.py guided --locations "Lobby,Hallway,Office 1"

# Build the HTML report
python survey_report.py

# Add a signal-strength heatmap over a floor plan
python survey_report.py --floorplan plan.png --coords coords.csv

# See a sample report in seconds — no wireless hardware needed
python survey_report.py --demo

# Compare two surveys (e.g. before and after an AP upgrade)
python compare_surveys.py --before before.csv --after after.csv --out compare.html

# Check this machine is ready to scan
python check_setup.py
```

Open `report.html` in a browser. Hand it to the client.

## How a survey works

1. Stand in the first spot, run `watch --location "Lobby"` for a few minutes.
2. Move to the next spot, change `--location`, repeat.
3. Run `survey_report.py` — you get per-location coverage cards, weak spots
   flagged below −70 dBm, and a channel utilization table showing congestion.

Or let the guided mode walk you through the spot list: at each location it
prompts you to walk there and press Enter, then scans and tags the reading
with that location automatically.

```bash
python wifi_survey.py guided --locations "Lobby,Hallway,Office 1"
python wifi_survey.py guided --locations sites.txt   # one location per line
```

`--ssid` filters to one network, same as `scan`/`watch`. Ctrl+C stops early;
everything scanned so far stays logged.

## What the report tells you

- **Coverage by location** — AP count, average signal, strongest APs per spot
- **Weak spots** — any location averaging below −70 dBm gets flagged
- **Channel utilization** — which channels are crowded, per band (2.4 / 5 / 6 GHz)

## Floor-plan heatmap

Give `survey_report.py` a floor-plan image and a coords file and the report
gains a signal-strength heatmap: each surveyed location is plotted on the plan
as a blurred dot colored by its average signal. The image is copied next to
`report.html` so the report stays portable.

```bash
python survey_report.py --floorplan plan.png --coords coords.csv
```

`coords.csv` maps each survey `--location` to its position on the plan as
0.0–1.0 fractions of the image width/height (`0,0` = top-left corner):

```csv
location,x,y
Lobby,0.20,0.75
Warehouse Aisle 3,0.55,0.40
Back Office,0.82,0.25
```

- Location names must match the `--location` labels used during the survey
  exactly; unmatched rows are skipped with a warning.
- Rows with missing or out-of-range (outside 0.0–1.0) coordinates are skipped.
- Omit `--floorplan`/`--coords` entirely and the report is built exactly as
  before — no heatmap section, no behavior change.

**Color scale** (same thresholds as the per-location badges):

| Average dBm | Dot color | Meaning |
|---|---|---|
| ≥ −50 | green `#28a745` | excellent |
| −50…−60 | light green `#5cb85c` | good |
| −60…−70 | yellow `#ffc107` | fair |
| < −70 | red `#dc3545` | weak |

Dots also scale with signal: stronger locations draw larger and more opaque.
Hover a dot in the report for the location name and its average dBm.

## Requirements

- Python 3.8+
- Windows: `netsh` (built in)
- Linux: `nmcli` (NetworkManager)
- macOS: `airport` utility (built in)

Run `python check_setup.py` before a survey — it prints plain-English
PASS/FAIL lines for the Python version, the scan tool on your platform, and
write access, and tells you plainly when this machine can't scan (you can
still build reports from existing CSVs or `--demo` data).

No pip packages required.

## Before/after comparison

Survey once before an AP upgrade and once after, then:

```bash
python compare_surveys.py --before before.csv --after after.csv --out compare.html
```

The comparison page shows, per location, the before/after signal badges
(same color thresholds as the survey report), the dBm delta, and a status:
**Improved** / **Degraded** / **Unchanged** (a move under ±3 dBm — adjustable
with `--threshold` — counts as unchanged), or **New location** / **Removed**
for spots present in only one dataset. It also prints the average change and
flags whether each spot crossed a coverage band. Add `--floorplan`/`--coords`
for side-by-side before/after heatmaps.

```bash
python compare_surveys.py --demo   # sample comparison from the bundled data
```

## Demo mode

No wireless hardware handy? `python survey_report.py --demo` builds the full
report — coverage cards, weak spots, channel table, and floor-plan heatmap —
from the bundled synthetic dataset in a few seconds. `compare_surveys.py --demo`
does the same for the comparison view. The demo files are
`demo_data.csv`, `demo_data_after.csv`, `demo_coords.csv`, `demo_plan.svg`.

## Files

| File | Purpose |
|---|---|
| `wifi_survey.py` | Cross-platform scanner: `scan`, `watch`, and `guided` modes, logs to `survey.csv` |
| `survey_report.py` | Builds `report.html` from `survey.csv` (`--demo` builds from bundled sample data) |
| `compare_surveys.py` | Builds `compare.html` before/after comparison from two survey CSVs |
| `check_setup.py` | PASS/FAIL readiness check: Python version, scan tool, write access |
| `demo_data.csv`, `demo_data_after.csv` | Bundled synthetic survey datasets for `--demo` |
| `demo_coords.csv`, `demo_plan.svg` | Bundled floor plan + coordinates for the `--demo` heatmap |
| `survey.csv` | Your measurements (created on first run, git-ignored) |
| `coords.csv` | Optional location → floor-plan x/y coordinates (see Floor-plan heatmap) |

## Example

```
$ python wifi_survey.py scan --ssid OfficeNet
SSID                         BSSID               SIG%      dBm    CHAN BAND     SECURITY
----------------------------------------------------------------------------------------------------
OfficeNet                    aa:bb:cc:11:22:33     82      -59       36 5GHz     WPA2
OfficeNet                    aa:bb:cc:44:55:66     64      -68        6 2.4GHz   WPA2
```

## License

MIT — use it on client jobs.
