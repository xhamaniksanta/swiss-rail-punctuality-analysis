"""Build the punctuality report and data quality findings from all collected snapshots.

Reads data/*.csv and writes reports/punctuality_dashboard.png,
reports/data_quality_findings.png and reports/summary.md.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = Path("data")
OUT_DIR = Path("reports")
ON_TIME_THRESHOLD = 3     # minutes, SBB definition
MAX_MINUTES_AHEAD = 15    # only departures close to leaving have a meaningful delay value
NAVY, BLUE = "#1a4070", "#4a7ab0"


def load():
    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        raise SystemExit("No data files found in data/. Run collect.py first.")
    raw = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    raw["snapshot_time"] = pd.to_datetime(raw["snapshot_time"], utc=True, errors="coerce")
    raw["planned_departure"] = pd.to_datetime(raw["planned_departure"], utc=True, errors="coerce")
    raw["forecast_departure"] = pd.to_datetime(raw["forecast_departure"], utc=True, errors="coerce")
    raw["delay_min"] = pd.to_numeric(raw["delay_min"], errors="coerce")
    return raw, len(files)


def analyse(raw):
    key = ["station_queried", "line", "destination", "planned_departure"]
    uniq = raw.sort_values("snapshot_time").drop_duplicates(subset=key, keep="last")

    quality_pct = {
        "Have real-time delay data": round(uniq["delay_min"].notna().mean() * 100, 1),
        "Forecast platform field filled": round(uniq["forecast_platform"].notna().mean() * 100, 1),
        "Station name differs from query": round((uniq["station_returned"] != uniq["station_queried"]).mean() * 100, 1),
        "Planned time missing or unreadable": round(uniq["planned_departure"].isna().mean() * 100, 1),
    }

    minutes_ahead = (uniq["planned_departure"] - uniq["snapshot_time"]).dt.total_seconds() / 60
    near = uniq[minutes_ahead <= MAX_MINUTES_AHEAD]
    clean = near.dropna(subset=["delay_min", "planned_departure"]).copy()
    clean["on_time"] = clean["delay_min"] < ON_TIME_THRESHOLD
    clean["hour"] = clean["planned_departure"].dt.tz_convert("Europe/Zurich").dt.hour
    clean["category"] = clean["category"].fillna("unknown")
    return uniq, clean, quality_pct


def group_stats(clean, by, min_count=1):
    return (clean.groupby(by)
            .agg(departures=("on_time", "size"),
                 on_time_pct=("on_time", lambda s: round(s.mean() * 100, 1)),
                 avg_delay_min=("delay_min", lambda s: round(s.mean(), 2)))
            .query("departures >= @min_count"))


def dashboard(clean, by_station, by_category, by_hour):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    axes[0, 0].hist(clean["delay_min"].clip(upper=15), bins=range(0, 17), color=NAVY, edgecolor="white")
    axes[0, 0].axvline(ON_TIME_THRESHOLD, color="#c0392b", linestyle="--", label="3 min threshold")
    axes[0, 0].set_title("Delay distribution (15+ grouped at 15)")
    axes[0, 0].set_xlabel("Delay (minutes)")
    axes[0, 0].set_ylabel("Departures")
    axes[0, 0].legend()

    s = by_station.sort_values("on_time_pct")
    axes[0, 1].barh(s.index, s["on_time_pct"], color=NAVY)
    axes[0, 1].set_title("On-time departures by station (%)")
    axes[0, 1].set_xlim(max(0, s["on_time_pct"].min() - 10), 100)
    for i, v in enumerate(s["on_time_pct"]):
        axes[0, 1].text(v + 0.3, i, f"{v}%", va="center")

    c = by_category.sort_values("on_time_pct")
    axes[1, 0].barh(c.index, c["on_time_pct"], color=BLUE)
    axes[1, 0].set_title("On-time departures by train type (%)")
    axes[1, 0].set_xlim(max(0, c["on_time_pct"].min() - 10), 100)
    for i, v in enumerate(c["on_time_pct"]):
        axes[1, 0].text(v + 0.3, i, f"{v}%", va="center")

    axes[1, 1].bar(by_hour.index.astype(str), by_hour["avg_delay_min"], color=NAVY)
    axes[1, 1].set_title("Average delay by planned departure hour")
    axes[1, 1].set_xlabel("Hour (Swiss time)")
    axes[1, 1].set_ylabel("Average delay (minutes)")

    fig.suptitle(f"Swiss rail punctuality: {len(clean)} departures at {clean['station_queried'].nunique()} stations",
                 fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "punctuality_dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def quality_chart(uniq, quality_pct):
    fig, ax = plt.subplots(figsize=(10, 4))
    q = pd.Series(quality_pct).sort_values()
    ax.barh(q.index, q.values, color=BLUE)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of unique departures")
    ax.set_title(f"Data quality check on {len(uniq)} unique departures")
    for i, v in enumerate(q.values):
        ax.text(v + 1, i, f"{v}%", va="center")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "data_quality_findings.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def write_summary(raw, uniq, clean, quality_pct, by_station, n_files):
    first = raw["snapshot_time"].min().tz_convert("Europe/Zurich")
    last = raw["snapshot_time"].max().tz_convert("Europe/Zurich")
    lines = [
        "# Latest results",
        "",
        f"Data from {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} (Swiss time), "
        f"{n_files} day file(s), {raw['snapshot_time'].nunique()} snapshots.",
        "",
        f"- Rows collected: {len(raw):,}",
        f"- Unique departures: {len(uniq):,}",
        f"- Departures analysed (close to departure, with delay data): {len(clean):,}",
        f"- On time (under {ON_TIME_THRESHOLD} min late): {clean['on_time'].mean() * 100:.1f}%",
        f"- Average delay: {clean['delay_min'].mean():.2f} min",
        f"- 5+ min late: {(clean['delay_min'] >= 5).mean() * 100:.1f}%",
        f"- Lowest on-time rate: {by_station['on_time_pct'].idxmin()} ({by_station['on_time_pct'].min()}%)",
        "",
        "## Data quality",
        "",
    ]
    lines += [f"- {name}: {value}%" for name, value in quality_pct.items()]
    (OUT_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    raw, n_files = load()
    uniq, clean, quality_pct = analyse(raw)
    if clean.empty:
        raise SystemExit("No departures with delay data yet. Collect more snapshots.")
    by_station = group_stats(clean, "station_queried")
    by_category = group_stats(clean, "category", min_count=10)
    if by_category.empty:
        by_category = group_stats(clean, "category")
    by_hour = group_stats(clean, "hour")
    dashboard(clean, by_station, by_category, by_hour)
    quality_chart(uniq, quality_pct)
    write_summary(raw, uniq, clean, quality_pct, by_station, n_files)
    print((OUT_DIR / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
