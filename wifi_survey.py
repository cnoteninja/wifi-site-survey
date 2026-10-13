#!/usr/bin/env python3
"""
wifi-survey: Wi-Fi site survey scanner.

Walks a site, logs every visible access point with signal strength, and tags
each measurement with a location label. Output feeds survey_report.py, which
builds a shareable HTML site-survey report.

Usage:
    python wifi_survey.py scan
        One-shot scan: print a table and append results to survey.csv.

    python wifi_survey.py watch --location "Lobby" --interval 10 --duration 5
        Log continuously for 5 minutes, one scan every 10 seconds, tagged
        "Lobby". Walk the site, changing --location at each spot you measure.

    python wifi_survey.py scan --ssid "OfficeNet"
        Only show/log one SSID (useful when surveying a specific deployment).

Works on Windows (netsh), Linux (nmcli, falls back to iwlist), macOS (airport).
No third-party dependencies.
"""

import argparse
import csv
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey.csv")
CSV_FIELDS = [
    "timestamp", "location", "ssid", "bssid", "signal_percent",
    "signal_dbm_est", "channel", "frequency_mhz", "band", "security", "platform",
]


def pct_to_dbm(pct):
    """Rough % -> dBm conversion used by most client drivers."""
    try:
        return round(int(pct) / 2 - 100, 1)
    except (TypeError, ValueError):
        return ""


def band_from_freq(freq_mhz):
    try:
        f = int(freq_mhz)
    except (TypeError, ValueError):
        return ""
    if 2400 <= f <= 2500:
        return "2.4GHz"
    if 5170 <= f <= 5835:
        return "5GHz"
    if 5945 <= f <= 7125:
        return "6GHz"
    return ""


def chan_to_freq(chan):
    """Best-effort channel -> center frequency (MHz)."""
    try:
        c = int(chan)
    except (TypeError, ValueError):
        return ""
    if 1 <= c <= 14:
        return 2412 + (c - 1) * 5 if c < 14 else 2484
    if 36 <= c <= 177:
        return 5180 + (c - 36) * 5
    return ""


# ---------------------------------------------------------------- Windows ----
def scan_windows():
    if not shutil.which("netsh"):
        return None, "netsh not found"
    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as exc:
        return None, str(exc)
    networks, current = [], {}
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"SSID \d+ : (.*)", line)
        if m:
            if current.get("ssid"):
                networks.append(current)
            current = {"ssid": m.group(1).strip(), "bssids": []}
        m = re.match(r"BSSID \d+\s+: ([0-9a-fA-F:]{17})", line)
        if m and current is not None:
            current["bssids"].append({"bssid": m.group(1), "signal": "", "channel": ""})
        m = re.match(r"Signal\s+: (\d+)%", line)
        if m and current.get("bssids"):
            current["bssids"][-1]["signal"] = m.group(1)
        m = re.match(r"Channel\s+: (\d+)", line)
        if m and current.get("bssids"):
            current["bssids"][-1]["channel"] = m.group(1)
    if current.get("ssid"):
        networks.append(current)
    rows = []
    for net in networks:
        for b in net["bssids"]:
            freq = chan_to_freq(b["channel"])
            rows.append({
                "ssid": net["ssid"], "bssid": b["bssid"],
                "signal_percent": b["signal"],
                "signal_dbm_est": pct_to_dbm(b["signal"]),
                "channel": b["channel"], "frequency_mhz": freq,
                "band": band_from_freq(freq), "security": "",
            })
    return rows, None


# ----------------------------------------------------------------- Linux ----
def scan_linux():
    if shutil.which("nmcli"):
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,CHAN,FREQ,BSSID,SECURITY",
                 "dev", "wifi", "list", "--rescan", "yes"],
                capture_output=True, text=True, timeout=45,
            ).stdout
        except Exception as exc:
            return None, str(exc)
        rows = []
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 6:
                continue
            ssid, sig, chan, freq, bssid = parts[0], parts[1], parts[2], parts[3], parts[4]
            security = ":".join(parts[5:])
            freq_num = re.sub(r"\D", "", freq)
            rows.append({
                "ssid": ssid, "bssid": bssid, "signal_percent": sig,
                "signal_dbm_est": pct_to_dbm(sig), "channel": chan,
                "frequency_mhz": freq_num, "band": band_from_freq(freq_num),
                "security": security,
            })
        return rows, None
    if shutil.which("iwlist"):
        return None, "iwlist fallback not implemented — install NetworkManager (nmcli)"
    return None, "nmcli not found (install NetworkManager)"


# ----------------------------------------------------------------- macOS ----
def scan_macos():
    airport = ("/System/Library/PrivateFrameworks/Apple80211.framework"
               "/Versions/Current/Resources/airport")
    if not os.path.exists(airport):
        return None, "airport utility not found"
    try:
        out = subprocess.run([airport, "-s"], capture_output=True,
                             text=True, timeout=30).stdout
    except Exception as exc:
        return None, str(exc)
    rows, lines = [], out.splitlines()[1:]
    for line in lines:
        # SSID may contain spaces; columns are: SSID BSSID RSSI CHANNEL HT CC SECURITY
        m = re.match(
            r"^(.+?)\s+([0-9a-fA-F:]{17})\s+(-?\d+)\s+(\d+)[,+]?.*\s+([A-Z]{2})\s+(.*)$",
            line.rstrip(),
        )
        if not m:
            continue
        ssid, bssid, rssi, chan, _cc, sec = m.groups()
        try:
            pct = max(0, min(100, 2 * (int(rssi) + 100)))
        except ValueError:
            pct = ""
        freq = chan_to_freq(chan)
        rows.append({
            "ssid": ssid.strip(), "bssid": bssid, "signal_percent": pct,
            "signal_dbm_est": rssi, "channel": chan, "frequency_mhz": freq,
            "band": band_from_freq(freq), "security": sec.strip(),
        })
    return rows, None


def scan():
    system = platform.system()
    if system == "Windows":
        return scan_windows()
    if system == "Linux":
        return scan_linux()
    if system == "Darwin":
        return scan_macos()
    return None, "unsupported platform: %s" % system


def append_csv(rows, location):
    new_file = not os.path.exists(CSV_PATH)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({
                "timestamp": ts, "location": location, "ssid": r["ssid"],
                "bssid": r["bssid"], "signal_percent": r["signal_percent"],
                "signal_dbm_est": r["signal_dbm_est"], "channel": r["channel"],
                "frequency_mhz": r["frequency_mhz"], "band": r["band"],
                "security": r["security"], "platform": platform.system(),
            })
    return len(rows)


def print_table(rows):
    print("%-28s %-18s %6s %8s %7s %-8s %s" % (
        "SSID", "BSSID", "SIG%", "dBm", "CHAN", "BAND", "SECURITY"))
    print("-" * 100)
    for r in sorted(rows, key=lambda x: str(x["signal_percent"]), reverse=True):
        print("%-28s %-18s %6s %8s %7s %-8s %s" % (
            r["ssid"][:28], r["bssid"], r["signal_percent"] or "-",
            r["signal_dbm_est"] or "-", r["channel"] or "-",
            r["band"] or "-", (r["security"] or "")[:24]))


def main():
    ap = argparse.ArgumentParser(description="Wi-Fi site survey scanner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="one-shot scan")
    p_scan.add_argument("--ssid", default="", help="only show this SSID")
    p_scan.add_argument("--location", default="", help="location label for this scan")

    p_watch = sub.add_parser("watch", help="log continuously")
    p_watch.add_argument("--location", required=True, help="location label (e.g. 'Lobby')")
    p_watch.add_argument("--interval", type=int, default=10, help="seconds between scans")
    p_watch.add_argument("--duration", type=int, default=5, help="total minutes to log")
    p_watch.add_argument("--ssid", default="", help="only log this SSID")

    args = ap.parse_args()
    filt = args.ssid.lower()

    if args.cmd == "scan":
        rows, err = scan()
        if err:
            print("scan failed: %s" % err, file=sys.stderr)
            sys.exit(1)
        rows = [r for r in rows if not filt or r["ssid"].lower() == filt]
        if not rows:
            print("no networks found" + (" matching '%s'" % args.ssid if filt else ""))
            sys.exit(0)
        print_table(rows)
        n = append_csv(rows, args.location)
        print("\nlogged %d readings -> %s" % (n, CSV_PATH))
    else:
        end = time.time() + args.duration * 60
        total = 0
        print("logging '%s' every %ds for %d min (Ctrl+C to stop)..."
              % (args.location, args.interval, args.duration))
        try:
            while time.time() < end:
                rows, err = scan()
                if err:
                    print("scan failed: %s" % err, file=sys.stderr)
                else:
                    rows = [r for r in rows if not filt or r["ssid"].lower() == filt]
                    total += append_csv(rows, args.location)
                    print("[%s] %d readings (%d total)"
                          % (datetime.now().strftime("%H:%M:%S"), len(rows), total))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        print("done: %d readings -> %s" % (total, CSV_PATH))


if __name__ == "__main__":
    main()
