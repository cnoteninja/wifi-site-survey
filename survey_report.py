#!/usr/bin/env python3
"""
survey_report: build a shareable HTML site-survey report from survey.csv.

Reads the CSV written by wifi_survey.py and produces report.html with:
  * per-location summary: AP count, strongest APs, average signal
  * weakest-spot flagging (avg signal below -70 dBm)
  * channel utilization per band (finds congestion / overlap)
  * full reading table

Usage:
    python survey_report.py [--csv survey.csv] [--out report.html] [--ssid OfficeNet]

No third-party dependencies.
"""

import argparse
import csv
import html
import os
from collections import defaultdict

CSV_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey.csv")


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load(csv_path, ssid_filter=""):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if ssid_filter and r.get("ssid", "").lower() != ssid_filter.lower():
                continue
            rows.append(r)
    return rows


def analyze(rows):
    by_loc = defaultdict(list)
    chan_use = defaultdict(lambda: defaultdict(set))  # band -> channel -> bssids
    for r in rows:
        by_loc[r.get("location") or "(unlabeled)"].append(r)
        band = r.get("band") or "unknown"
        chan = r.get("channel") or "?"
        if r.get("bssid"):
            chan_use[band][chan].add(r["bssid"])

    loc_summary = []
    for loc, rs in sorted(by_loc.items()):
        dbms = [num(r.get("signal_dbm_est")) for r in rs]
        dbms = [d for d in dbms if d is not None]
        bssids = {r["bssid"] for r in rs if r.get("bssid")}
        ssids = {r["ssid"] for r in rs if r.get("ssid")}
        # strongest reading per BSSID
        best = {}
        for r in rs:
            d = num(r.get("signal_dbm_est"))
            if d is None or not r.get("bssid"):
                continue
            if r["bssid"] not in best or d > best[r["bssid"]][0]:
                best[r["bssid"]] = (d, r["ssid"], r.get("channel"))
        top = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:5]
        avg = sum(dbms) / len(dbms) if dbms else None
        loc_summary.append({
            "location": loc, "readings": len(rs), "aps": len(bssids),
            "ssids": len(ssids), "avg_dbm": avg,
            "weak": avg is not None and avg < -70, "top": top,
        })

    chan_summary = []
    for band in sorted(chan_use):
        for chan in sorted(chan_use[band], key=lambda c: (c == "?", c)):
            chan_summary.append({
                "band": band, "channel": chan,
                "ap_count": len(chan_use[band][chan]),
            })
    chan_summary.sort(key=lambda c: c["ap_count"], reverse=True)
    return loc_summary, chan_summary


def badge(avg):
    if avg is None:
        return "<span class='b'>n/a</span>"
    if avg >= -50:
        cls, label = "g", "Excellent"
    elif avg >= -60:
        cls, label = "g", "Good"
    elif avg >= -70:
        cls, label = "y", "Fair"
    else:
        cls, label = "r", "Weak"
    return "<span class='b %s'>%.0f dBm (%s)</span>" % (cls, avg, label)


def build_html(loc_summary, chan_summary, rows, title):
    e = html.escape
    loc_cards = []
    for loc in loc_summary:
        flag = " <span class='b r'>WEAK SPOT</span>" if loc["weak"] else ""
        top_rows = "".join(
            "<tr><td>%s</td><td><code>%s</code></td><td>%s</td><td>%.0f dBm</td></tr>" % (
                e(ssid), e(bssid), e(str(chan)), dbm)
            for bssid, (dbm, ssid, chan) in loc["top"])
        loc_cards.append(
            "<div class='card'><h3>%s%s</h3>"
            "<p>%d readings · %d APs · %d SSIDs · avg %s</p>"
            "<table><tr><th>SSID</th><th>BSSID</th><th>Ch</th><th>Best signal</th></tr>%s</table></div>"
            % (e(loc["location"]), flag, loc["readings"], loc["aps"],
               loc["ssids"], badge(loc["avg_dbm"]), top_rows))

    chan_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%d APs</td><td>%s</td></tr>" % (
            e(c["band"]), e(str(c["channel"])), c["ap_count"],
            "<span class='b r'>congested</span>" if c["ap_count"] >= 4 else "")
        for c in chan_summary[:20])

    all_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td>"
        "<td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(r.get("timestamp", "")[:16]), e(r.get("location", "")),
            e(r.get("ssid", "")), e(r.get("bssid", "")),
            e(str(r.get("signal_dbm_est", ""))), e(str(r.get("channel", ""))),
            e(r.get("band", "")))
        for r in rows[-500:])

    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2em auto;padding:0 1em;color:#222}}
.card{{border:1px solid #ddd;border-radius:8px;padding:1em;margin:1em 0}}
table{{border-collapse:collapse;width:100%;margin:.5em 0}}
th,td{{border:1px solid #ddd;padding:.4em .6em;text-align:left;font-size:.9em}}
th{{background:#f5f5f5}}
.b{{padding:.15em .5em;border-radius:4px;font-size:.85em;font-weight:bold}}
.g{{background:#d4edda}}.y{{background:#fff3cd}}.r{{background:#f8d7da}}
code{{font-size:.85em}}
</style></head><body>
<h1>{t}</h1>
<p>{n} readings across {l} locations.</p>
<h2>Coverage by location</h2>
{cards}
<h2>Channel utilization (most crowded first)</h2>
<table><tr><th>Band</th><th>Channel</th><th>APs heard</th><th></th></tr>{chans}</table>
<h2>All readings (last 500)</h2>
<table><tr><th>Time</th><th>Location</th><th>SSID</th><th>BSSID</th>
<th>dBm</th><th>Ch</th><th>Band</th></tr>{allr}</table>
<p><small>Generated by <a href="https://github.com/cnoteninja/wifi-site-survey">wifi-site-survey</a>.
Signal thresholds: ≥-50 excellent, -60 good, -70 fair, below -70 weak.</small></p>
</body></html>""".format(
        t=e(title), n=len(rows), l=len(loc_summary),
        cards="".join(loc_cards), chans=chan_rows, allr=all_rows)


def main():
    ap = argparse.ArgumentParser(description="Build HTML site-survey report")
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--out", default="report.html")
    ap.add_argument("--ssid", default="", help="only include this SSID")
    ap.add_argument("--title", default="Wi-Fi Site Survey Report")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print("no data: %s not found — run wifi_survey.py first" % args.csv)
        raise SystemExit(1)
    rows = load(args.csv, args.ssid)
    if not rows:
        print("no readings in %s" % args.csv)
        raise SystemExit(1)
    loc_summary, chan_summary = analyze(rows)
    out = os.path.join(os.path.dirname(os.path.abspath(args.out)), args.out) \
        if not os.path.isabs(args.out) else args.out
    outdir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(outdir, os.path.basename(args.out))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html(loc_summary, chan_summary, rows, args.title))
    weak = [l["location"] for l in loc_summary if l["weak"]]
    print("wrote %s (%d readings, %d locations)" % (out, len(rows), len(loc_summary)))
    if weak:
        print("weak spots (avg < -70 dBm): " + ", ".join(weak))


if __name__ == "__main__":
    main()
