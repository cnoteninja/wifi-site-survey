#!/usr/bin/env python3
"""
check_setup: plain-English readiness check for wifi-site-survey.

Prints PASS/FAIL lines (never a traceback) covering:
  * Python version (>= 3.8)
  * platform support (Windows / Linux / macOS)
  * the wireless scan tool wifi_survey.py needs on this machine
    (netsh / nmcli / airport) — with platform-aware guidance when missing
  * write access to the survey directory
  * bundled demo data presence (so reports work even with no hardware)

Run it before a survey: `python check_setup.py`
"""

import os
import platform
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

AIRPORT = ("/System/Library/PrivateFrameworks/Apple80211.framework"
           "/Versions/Current/Resources/airport")


def tool_for_platform(system):
    """(tool name, how to find it, plain-English install hint)."""
    if system == "Windows":
        return ("netsh",
                lambda: shutil.which("netsh") is not None,
                "netsh ships with Windows — run this check from a normal "
                "Command Prompt / PowerShell, not a minimal container.")
    if system == "Linux":
        return ("nmcli",
                lambda: shutil.which("nmcli") is not None,
                "install NetworkManager (e.g. `sudo apt install network-manager`). "
                "Note: this repo's iwlist fallback is not implemented, so nmcli "
                "is the only supported Linux scanner.")
    if system == "Darwin":
        return ("airport utility",
                lambda: os.path.exists(AIRPORT),
                "the airport utility ships with macOS — run this check on the "
                "Mac itself, not over a remote shell.")
    return (None, None, None)


def main():
    print("wifi-site-survey setup check\n")
    passes, fails = 0, 0

    def report(ok, label, detail=""):
        line = "PASS" if ok else "FAIL"
        print("%s: %s%s" % (line, label, (" — " + detail) if detail else ""))
        return ok

    # 1. Python version
    try:
        ok = sys.version_info >= (3, 8)
        if report(ok, "Python %s" % platform.python_version().split()[0],
                  "3.8+ required" if not ok else "3.8+ required"):
            passes += 1
        else:
            fails += 1
    except Exception:
        print("FAIL: could not determine Python version")

    # 2. Platform support
    system = platform.system()
    try:
        if system in ("Windows", "Linux", "Darwin"):
            print("PASS: supported platform (%s)" % system)
            passes += 1
        else:
            print("FAIL: unsupported platform (%s) — scanning works on "
                  "Windows, Linux and macOS only" % system)
            fails += 1
    except Exception:
        print("FAIL: could not determine platform")
        fails += 1

    # 3. Wireless scan tool
    try:
        name, probe, hint = tool_for_platform(system)
        if name is None:
            print("FAIL: no scan tool to check on this platform")
            fails += 1
        elif probe():
            print("PASS: scan tool found (%s)" % name)
            passes += 1
        else:
            print("FAIL: no wireless scan tool on this machine (%s not found)" % name)
            print("      %s" % hint)
            if system == "Linux" and shutil.which("iwlist"):
                print("      iwlist is present, but this repo only scans via nmcli.")
            print("      You can still build reports from existing CSVs, or run "
                  "`python survey_report.py --demo` to see a sample report.")
            fails += 1
    except Exception as exc:
        print("FAIL: could not check scan tool (%s)" % exc)
        fails += 1

    # 4. Write access to the survey directory
    try:
        fd, tmp = tempfile.mkstemp(dir=HERE, prefix=".writetest")
        os.close(fd)
        os.remove(tmp)
        print("PASS: survey directory is writable (%s)" % HERE)
        passes += 1
    except Exception:
        print("FAIL: cannot write to %s — scans and reports cannot save there" % HERE)
        fails += 1

    # 5. Demo data present
    try:
        demo = all(os.path.exists(os.path.join(HERE, f))
                   for f in ("demo_data.csv", "demo_data_after.csv",
                             "demo_coords.csv", "demo_plan.svg"))
        if demo:
            print("PASS: demo data found — `python survey_report.py --demo` "
                  "works with no wireless hardware")
            passes += 1
        else:
            print("FAIL: demo files missing from the repo directory")
            fails += 1
    except Exception:
        print("FAIL: could not check demo data")
        fails += 1

    print("\n%d passed, %d failed" % (passes, fails))
    if fails == 0:
        print("READY TO SCAN — try: python wifi_survey.py scan")
    else:
        print("REPORT-ONLY MODE — scanning is unavailable, but you can still "
              "generate reports from existing CSVs or --demo data.")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
