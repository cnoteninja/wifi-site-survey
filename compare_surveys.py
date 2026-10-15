#!/usr/bin/env python3
"""
compare_surveys: before/after Wi-Fi survey comparison.

Takes two survey CSVs (as written by wifi_survey.py) and builds an HTML
delta view: per-location signal change with dBm deltas, badge colors and
weak-spot thresholds matching survey_report.py, plus side-by-side signal
heatmaps when --floorplan/--coords are given.

Usage:
    python compare_surveys.py --before before.csv --after after.csv [--out compare.html]
    python compare_surveys.py --demo [--out compare.html]
    python compare_surveys.py --before b.csv --after a.csv \\
        --floorplan plan.png --coords coords.csv

Locations present in only one dataset are marked "new" (after only) or
"removed" (before only). A location whose average signal moved less than
--threshold dBm either way counts as "unchanged".

No third-party dependencies.
"""

import argparse
import html
import os
import shutil
import sys

from survey_report import (CSS_BASE, DEMO_COORDS, DEMO_CSV, DEMO_DIR,
                           analyze, badge, heatmap_html, load, load_coords)

DEMO_AFTER = os.path.join(DEMO_DIR, "demo_data_after.csv")
DEMO_PLAN = os.path.join(DEMO_DIR, "demo_plan.svg")
DEFAULT_THRESHOLD = 3.0  # dBm; smaller moves count as "unchanged"


def compare_locations(before_summary, after_summary, threshold=DEFAULT_THRESHOLD):
    """Diff two per-location summaries into delta rows.

    Each row: location, before/after avg dBm, delta, status label + badge
    class, and AP counts. Statuses: improved / degraded / unchanged /
    new / removed.
    """
    before = {l["location"]: l for l in before_summary}
    after = {l["location"]: l for l in after_summary}
    rows = []
    for loc in sorted(set(before) | set(after), key=str.lower):
        b, a = before.get(loc), after.get(loc)
        if a is None:
            rows.append({"location": loc, "before": b, "after": None,
                         "delta": None, "status": "Removed", "cls": "n"})
        elif b is None:
            rows.append({"location": loc, "before": None, "after": a,
                         "delta": None, "status": "New location", "cls": "y"})
        elif b["avg_dbm"] is None or a["avg_dbm"] is None:
            rows.append({"location": loc, "before": b, "after": a,
                         "delta": None, "status": "No signal data", "cls": "n"})
        else:
            delta = a["avg_dbm"] - b["avg_dbm"]
            if delta >= threshold:
                status, cls = "Improved", "g"
            elif delta <= -threshold:
                status, cls = "Degraded", "r"
            else:
                status, cls = "Unchanged", "n"
            rows.append({"location": loc, "before": b, "after": a,
                         "delta": delta, "status": status, "cls": cls})
    rank = {"Improved": 0, "Degraded": 1, "New location": 2,
            "Removed": 3, "No signal data": 4, "Unchanged": 5}
    rows.sort(key=lambda r: (rank[r["status"]],
                             -(r["delta"] if r["delta"] is not None else -999)))
    return rows


def status_badge(row):
    if row["status"] in ("New location", "Removed"):
        return "<span class='b %s'>%s</span>" % (row["cls"], row["status"])
    if row["delta"] is None:
        return "<span class='b n'>%s</span>" % row["status"]
    sign = "+" if row["delta"] >= 0 else ""
    return ("<span class='b %s'>%s</span> (%s%.0f dBm)"
            % (row["cls"], row["status"], sign, row["delta"]))


def delta_row(row):
    e = html.escape
    before = badge(row["before"]["avg_dbm"]) if row["before"] else "&mdash;"
    after = badge(row["after"]["avg_dbm"]) if row["after"] else "&mdash;"
    ap_txt = "%s &rarr; %s" % (
        row["before"]["aps"] if row["before"] else "&mdash;",
        row["after"]["aps"] if row["after"] else "&mdash;")
    return ("<tr><td><strong>%s</strong></td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td></tr>"
            % (e(row["location"]), before, after, status_badge(row), ap_txt))


def build_compare_html(deltas, title, before_hm="", after_hm=""):
    e = html.escape
    matched = [d for d in deltas if d["delta"] is not None]
    counts = {}
    for d in deltas:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    if matched:
        avg_delta = sum(d["delta"] for d in matched) / len(matched)
        summary = ("Average change across %d matched locations: "
                   "<strong>%+.1f dBm</strong>. " % (len(matched), avg_delta))
    else:
        summary = "No locations appear in both surveys, so no deltas to show. "
    summary += " · ".join("%s: %d" % (s, counts[s]) for s in
                          ("Improved", "Degraded", "Unchanged",
                           "New location", "Removed") if s in counts)

    heatmaps = ""
    if before_hm or after_hm:
        heatmaps = ("<h2>Heatmaps</h2><div class='twocol'>"
                    "<div>%s</div><div>%s</div></div>"
                    % (before_hm.replace("<h2>Signal heatmap</h2>",
                                         "<h2>Before</h2>", 1),
                       after_hm.replace("<h2>Signal heatmap</h2>",
                                        "<h2>After</h2>", 1)))

    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t}</title>
<style>{css}</style></head><body>
<h1>{t}</h1>
<p>{s}</p>
{heat}
<h2>Signal change by location</h2>
<table><tr><th>Location</th><th>Before</th><th>After</th><th>Change</th>
<th>APs</th></tr>{rows}</table>
<p><small>Generated by <a href="https://github.com/cnoteninja/wifi-site-survey">wifi-site-survey</a>.
Badge thresholds: ≥-50 excellent, -60 good, -70 fair, below -70 weak.
A move under ±{thr:.0f} dBm counts as unchanged.</small></p>
</body></html>""".format(
        t=e(title), css=CSS_BASE, s=summary, heat=heatmaps,
        thr=DEFAULT_THRESHOLD, rows="".join(delta_row(d) for d in deltas))


def copy_plan(floorplan, outdir):
    """Copy the floor-plan image next to the report; return its file name."""
    img_name = os.path.basename(floorplan)
    dest = os.path.join(outdir, img_name)
    if os.path.abspath(floorplan) != os.path.abspath(dest):
        shutil.copy(floorplan, dest)
    return img_name


def main():
    ap = argparse.ArgumentParser(description="Before/after Wi-Fi survey comparison")
    ap.add_argument("--before", default="",
                    help="CSV from the 'before' survey")
    ap.add_argument("--after", default="",
                    help="CSV from the 'after' survey")
    ap.add_argument("--out", default="compare.html")
    ap.add_argument("--ssid", default="", help="only include this SSID")
    ap.add_argument("--title", default="Wi-Fi Site Survey Comparison")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="dBm change counted as a real improvement/degradation "
                         "(default %.0f)" % DEFAULT_THRESHOLD)
    ap.add_argument("--floorplan", default="",
                    help="floor-plan image for side-by-side heatmaps")
    ap.add_argument("--coords", default="",
                    help="CSV of location,x,y (0.0-1.0 fractions of the plan image)")
    ap.add_argument("--demo", action="store_true",
                    help="compare the bundled before/after demo datasets "
                         "(no wireless hardware needed)")
    args = ap.parse_args()

    if args.demo:
        args.before = args.before or DEMO_CSV
        args.after = args.after or DEMO_AFTER
        args.floorplan = args.floorplan or DEMO_PLAN
        args.coords = args.coords or DEMO_COORDS
        if args.title == "Wi-Fi Site Survey Comparison":
            args.title = "Wi-Fi Site Survey Comparison (Demo Data)"

    if not args.before or not args.after:
        print("need --before and --after CSVs (or use --demo)")
        raise SystemExit(1)
    for label, path in (("before", args.before), ("after", args.after)):
        if not os.path.exists(path):
            print("%s data not found: %s" % (label, path))
            raise SystemExit(1)
    before_rows = load(args.before, args.ssid)
    after_rows = load(args.after, args.ssid)
    if not before_rows:
        print("no readings in %s" % args.before)
        raise SystemExit(1)
    if not after_rows:
        print("no readings in %s" % args.after)
        raise SystemExit(1)

    before_sum, _ = analyze(before_rows)
    after_sum, _ = analyze(after_rows)
    deltas = compare_locations(before_sum, after_sum, args.threshold)

    outdir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(outdir, os.path.basename(args.out))

    before_hm = after_hm = ""
    if args.floorplan and args.coords:
        if not os.path.exists(args.coords):
            print("coords file not found: %s" % args.coords, file=sys.stderr)
            raise SystemExit(1)
        coords = load_coords(args.coords)
        img_name = copy_plan(args.floorplan, outdir)
        before_hm = heatmap_html(before_sum, coords, img_name)
        after_hm = heatmap_html(after_sum, coords, img_name)

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_compare_html(deltas, args.title, before_hm, after_hm))
    matched = [d for d in deltas if d["delta"] is not None]
    avg = sum(d["delta"] for d in matched) / len(matched) if matched else 0
    print("wrote %s (%d locations, avg change %+.1f dBm)"
          % (out, len(deltas), avg))


if __name__ == "__main__":
    main()
