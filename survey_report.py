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
    python survey_report.py --floorplan plan.png --coords coords.csv

    --floorplan/--coords render a signal-strength heatmap over the floor-plan
    image (copied next to report.html). coords.csv format:
        location,x,y
        Lobby,0.20,0.75
    with x,y as 0.0-1.0 fractions of the plan image (0,0 = top-left).

No third-party dependencies.
"""

import argparse
import csv
import html
import os
import shutil
import sys
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


def load_coords(path):
    """Load location -> (x, y) fractions from a coords CSV.

    Format: header `location,x,y` where x and y are 0.0-1.0 fractions of the
    floor-plan image's width/height (0,0 = top-left corner). Example:

        location,x,y
        Lobby,0.20,0.75
        Warehouse Aisle 3,0.55,0.40
    """
    coords = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            loc = (r.get("location") or "").strip()
            x, y = num(r.get("x")), num(r.get("y"))
            if not loc or x is None or y is None:
                print("warning: skipping bad coords row: %r" % (r,), file=sys.stderr)
                continue
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                print("warning: coords out of 0.0-1.0 range, skipping: %r" % (r,),
                      file=sys.stderr)
                continue
            coords[loc] = (x, y)
    return coords


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


def dbm_color(avg):
    """Green -> yellow -> red heatmap color for a dBm average.

    Mirrors the badge thresholds: >=-50 excellent, -50..-60 good,
    -60..-70 fair, below -70 weak.
    """
    if avg is None:
        return "#999999"
    if avg >= -50:
        return "#28a745"
    if avg >= -60:
        return "#5cb85c"
    if avg >= -70:
        return "#ffc107"
    return "#dc3545"


def heatmap_html(loc_summary, coords, img_name):
    """Render the floor-plan image with a signal-strength dot overlay.

    Each surveyed location with coords gets a blurred radial dot positioned
    at its x/y fraction of the image; stronger signals draw larger and more
    opaque. Returns "" when there is nothing to plot.
    """
    dots = []
    for loc in loc_summary:
        xy = coords.get(loc["location"])
        if not xy or loc["avg_dbm"] is None:
            continue
        x, y = xy
        color = dbm_color(loc["avg_dbm"])
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        strength = max(0.0, min(1.0, (loc["avg_dbm"] + 100) / 70.0))  # 0 weak .. 1 strong
        size = 8 + 14 * strength      # dot diameter, % of map width
        opacity = 0.35 + 0.45 * strength
        dots.append(
            "<div class='dot' title='%s: %.0f dBm' style='left:%.1f%%;top:%.1f%%;"
            "width:%.1f%%;background:radial-gradient(circle,"
            " rgba(%d,%d,%d,%.2f) 0%%, rgba(%d,%d,%d,0) 70%%)'></div>"
            % (html.escape(loc["location"]), loc["avg_dbm"],
               x * 100, y * 100, size, r, g, b, opacity, r, g, b))
    if not dots:
        return ""
    return ("<h2>Signal heatmap</h2>"
            "<div class='mapwrap'><img class='plan' src='%s' alt='floor plan'>%s</div>"
            "<p class='legend'>"
            "<span class='sw' style='background:#28a745'></span>&ge;-50 excellent"
            "<span class='sw' style='background:#5cb85c'></span>-50&hellip;-60 good"
            "<span class='sw' style='background:#ffc107'></span>-60&hellip;-70 fair"
            "<span class='sw' style='background:#dc3545'></span>&lt;-70 weak</p>"
            % (html.escape(img_name, quote=True), "".join(dots)))


def build_html(loc_summary, chan_summary, rows, title, heatmap=""):
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
.mapwrap{{position:relative;max-width:800px;margin:1em 0}}
.mapwrap img.plan{{display:block;width:100%;height:auto;border:1px solid #ddd;border-radius:8px}}
.dot{{position:absolute;transform:translate(-50%,-50%);aspect-ratio:1;border-radius:50%}}
.legend{{font-size:.9em}}
.sw{{display:inline-block;width:.9em;height:.9em;border-radius:3px;margin:0 .3em 0 1em;vertical-align:baseline}}
</style></head><body>
<h1>{t}</h1>
<p>{n} readings across {l} locations.</p>
{heat}
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
        t=e(title), n=len(rows), l=len(loc_summary), heat=heatmap,
        cards="".join(loc_cards), chans=chan_rows, allr=all_rows)


def main():
    ap = argparse.ArgumentParser(description="Build HTML site-survey report")
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--out", default="report.html")
    ap.add_argument("--ssid", default="", help="only include this SSID")
    ap.add_argument("--title", default="Wi-Fi Site Survey Report")
    ap.add_argument("--floorplan", default="",
                    help="floor-plan image to overlay a signal heatmap on")
    ap.add_argument("--coords", default="",
                    help="CSV of location,x,y (0.0-1.0 fractions of the plan image)")
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

    heatmap = ""
    if args.floorplan and args.coords:
        if not os.path.exists(args.coords):
            print("coords file not found: %s" % args.coords, file=sys.stderr)
            raise SystemExit(1)
        coords = load_coords(args.coords)
        img_name = os.path.basename(args.floorplan)
        dest = os.path.join(outdir, img_name)
        if os.path.abspath(args.floorplan) != os.path.abspath(dest):
            shutil.copy(args.floorplan, dest)
        heatmap = heatmap_html(loc_summary, coords, img_name)
        if not heatmap:
            print("warning: no plotted locations — check coords match survey location names",
                  file=sys.stderr)
    elif args.floorplan or args.coords:
        print("warning: heatmap needs both --floorplan and --coords; skipping",
              file=sys.stderr)

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html(loc_summary, chan_summary, rows, args.title, heatmap))
    weak = [l["location"] for l in loc_summary if l["weak"]]
    print("wrote %s (%d readings, %d locations)" % (out, len(rows), len(loc_summary)))
    if weak:
        print("weak spots (avg < -70 dBm): " + ", ".join(weak))


if __name__ == "__main__":
    main()
