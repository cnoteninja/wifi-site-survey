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

# Build the HTML report
python survey_report.py
```

Open `report.html` in a browser. Hand it to the client.

## How a survey works

1. Stand in the first spot, run `watch --location "Lobby"` for a few minutes.
2. Move to the next spot, change `--location`, repeat.
3. Run `survey_report.py` — you get per-location coverage cards, weak spots
   flagged below −70 dBm, and a channel utilization table showing congestion.

## What the report tells you

- **Coverage by location** — AP count, average signal, strongest APs per spot
- **Weak spots** — any location averaging below −70 dBm gets flagged
- **Channel utilization** — which channels are crowded, per band (2.4 / 5 / 6 GHz)

## Requirements

- Python 3.8+
- Windows: `netsh` (built in)
- Linux: `nmcli` (NetworkManager)
- macOS: `airport` utility (built in)

No pip packages required.

## Files

| File | Purpose |
|---|---|
| `wifi_survey.py` | Cross-platform scanner: `scan` and `watch` modes, logs to `survey.csv` |
| `survey_report.py` | Builds `report.html` from `survey.csv` |
| `survey.csv` | Your measurements (created on first run, git-ignored) |

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
