"""Collect one snapshot of Swiss station departures and append it to today's CSV.

Runs once per call. GitHub Actions calls it every 15 minutes (see
.github/workflows/collect.yml). Data source: https://transport.opendata.ch
"""
import csv
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://transport.opendata.ch/v1"
STATIONS = ["Zürich HB", "Bern", "Basel SBB", "Genève", "Lausanne",
            "Luzern", "Winterthur", "St. Gallen"]

DEPARTURES_PER_STATION = 40   # enough to cover the next ~20 minutes at the busiest stations
KEEP_MINUTES_AHEAD = 20       # only keep departures that are about to leave
DATA_DIR = Path("data")
TZ = ZoneInfo("Europe/Zurich")

FIELDS = ["snapshot_time", "station_queried", "station_returned", "category", "number",
          "line", "operator", "destination", "planned_departure", "forecast_departure",
          "delay_min", "planned_platform", "forecast_platform"]


def get_json(endpoint, params, retries=3, wait=5):
    """GET with retries. Returns parsed JSON, or None if the request failed."""
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=20)
        except requests.exceptions.RequestException as e:
            print(f"  attempt {attempt}: connection problem ({e.__class__.__name__})")
            time.sleep(wait)
            continue
        if r.status_code == 200:
            return r.json()
        if 400 <= r.status_code < 500:
            print(f"  {r.status_code} client error for {params}: not retrying")
            return None
        print(f"  attempt {attempt}: {r.status_code} server error, retrying in {wait}s")
        time.sleep(wait)
    return None


def flatten_departure(dep, station_queried, snapshot_time):
    stop = dep.get("stop") or {}
    prog = stop.get("prognosis") or {}
    return {
        "snapshot_time": snapshot_time,
        "station_queried": station_queried,
        "station_returned": (stop.get("station") or {}).get("name"),
        "category": dep.get("category"),
        "number": dep.get("number"),
        "line": f"{dep.get('category') or ''} {dep.get('number') or ''}".strip(),
        "operator": dep.get("operator"),
        "destination": dep.get("to"),
        "planned_departure": stop.get("departure"),
        "forecast_departure": prog.get("departure"),
        "delay_min": stop.get("delay"),
        "planned_platform": stop.get("platform"),
        "forecast_platform": prog.get("platform"),
    }


def minutes_until(planned_departure, now):
    """Minutes from now until the planned departure, or None if the time can't be read."""
    try:
        planned = datetime.strptime(planned_departure, "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None
    return (planned - now).total_seconds() / 60


def collect_snapshot():
    now = datetime.now(TZ)
    snapshot_time = now.isoformat(timespec="seconds")
    rows = []
    for station in STATIONS:
        data = get_json("stationboard", {"station": station, "limit": DEPARTURES_PER_STATION})
        if not data:
            print(f"  no data for {station}")
            continue
        for dep in data.get("stationboard") or []:
            row = flatten_departure(dep, station, snapshot_time)
            ahead = minutes_until(row["planned_departure"], now)
            # Unreadable times are kept on purpose: they are a data quality finding.
            if ahead is None or ahead <= KEEP_MINUTES_AHEAD:
                rows.append(row)
        time.sleep(1)  # be polite to a free public API
    return rows, now


def append_rows(rows, now):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{now:%Y-%m-%d}.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    rows, now = collect_snapshot()
    if not rows:
        # Fail the run so a broken API shows up as a red cross in the Actions tab.
        raise SystemExit("No rows collected: the API returned nothing for any station.")
    path = append_rows(rows, now)
    print(f"Saved {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
