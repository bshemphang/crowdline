#!/usr/bin/env python3
"""Crowdline: hour-by-hour Twitch audience forecaster for big game launch days.

Reads one case file per run (/input/<id>.in, or $MAKEFUN_INPUT_DIR) and writes
one forecast (/output/<id>.out, or $MAKEFUN_OUTPUT_DIR): for each of hours 2
to 24 of the launch day, five quantiles (5%, 25%, 50%, 75%, 95%) of that
hour's concurrent Twitch viewers in the game's category.

Model: the launch-day audience curve is mostly a shape, not a level. The
level comes from the case's own hour-1 print; the shape comes from the
comparables, past big launches' hourly curves shipped in the case. For each
hour h, every comparable contributes the ratio of its hour-h viewers to its
own hour-1 viewers, weighted by how close its scale is to the target's:
mega-launches hold their audience through the night while small ones fade,
so the weight is a Gaussian kernel in log space over the hour-1 prints. The
forecast median for hour h is the hour-1 print times the weighted median
ratio across comparables, and the spread is the weighted spread of those
ratios in log space. Quantiles are the median times exp(z * spread) with the
standard normal quantiles, so the band is honest about how much launch days
disagree with each other. No network, no randomness, no clock: two runs on
the same case produce the same bytes.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

# Standard normal quantiles at the case's levels (0.05, 0.25, 0.5, 0.75, 0.95).
Z = (-1.645, -0.674, 0.0, 0.674, 1.645)

# Spread floor: even the most predictable hour keeps some uncertainty.
SPREAD_FLOOR = 0.15
# Spread cap: beyond this the band is so wide it stops meaning anything.
SPREAD_CAP = 1.0

MAX_VIEWERS = 1_000_000_000


def parse_time(text):
    """Parse an ISO 8601 UTC timestamp into an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_viewers(comparable):
    """Return {hour: viewers} for the comparable's release day, hours 1..24.

    A comparable's hourly array runs from 14 days before its release day to
    3 days after it. Only the 24 hours starting at day_start count.
    Returns None when the comparable has no usable hour-1 print.
    """
    try:
        t0 = parse_time(comparable["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    hours = {}
    for row in comparable.get("hourly") or []:
        try:
            when = parse_time(row["from"])
            viewers = row["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        delta = when - t0
        if timedelta(0) <= delta < timedelta(hours=24):
            hour = int(delta.total_seconds() // 3600) + 1
            if isinstance(viewers, (int, float)) and viewers > 0:
                hours[hour] = float(viewers)
    if hours.get(1, 0) <= 0:
        return None
    return hours


def comparable_days(comparables):
    """Return [(hour1, {hour: viewers})] for comparables with a usable print."""
    days = []
    for comparable in comparables or []:
        day = release_day_viewers(comparable)
        if day is None:
            continue
        days.append((day[1], day))
    return days


def kernel_weight(comp_first, target_first):
    """Similarity weight: launches near the target's scale count most.

    A Gaussian kernel in log space with a bandwidth of 1.0 log units, so a
    comparable whose hour-1 print is within ~2.7x of the target's keeps most
    of its weight, and one ten times larger or smaller keeps almost none.
    Launch shape depends on scale: mega-launches hold their audience through
    the night while small ones fade, so an unweighted median mixes shapes
    that do not belong together.
    """
    return math.exp(-0.5 * (math.log(comp_first / target_first) / 1.0) ** 2)


def weighted_median(pairs):
    """Median of values with weights; pairs is [(value, weight)]."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return None
    half = total / 2.0
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= half:
            return value
    return ordered[-1][0]


def weighted_stdev(pairs):
    """Weighted standard deviation of log values; pairs is [(value, weight)]."""
    total = sum(w for _, w in pairs)
    if total <= 0 or len(pairs) < 2:
        return None
    mean = sum(w * math.log(v) for v, w in pairs) / total
    var = sum(w * (math.log(v) - mean) ** 2 for v, w in pairs) / total
    return math.sqrt(max(var, 0.0))


def forecast_case(case):
    """Forecast hours 2..24 of one case as 23 rows of five quantiles."""
    known = case.get("known") or []
    print1 = 1.0
    if known:
        try:
            print1 = float(known[0].get("viewers") or 0)
        except (TypeError, ValueError):
            print1 = 0.0
    if not (print1 > 0):
        print1 = 1.0

    days = comparable_days(case.get("comparables"))
    rows = []
    for hour in range(2, 25):
        pairs = []
        for first, day in days:
            value = day.get(hour)
            if value is not None and value > 0:
                pairs.append((value / first, kernel_weight(first, print1)))
        if pairs:
            median_ratio = weighted_median(pairs)
            spread = weighted_stdev(pairs)
            if spread is None:
                spread = SPREAD_FLOOR
        else:
            # No comparable printed that hour: stay flat, widen like the
            # house baseline does.
            median_ratio = 1.0
            spread = SPREAD_FLOOR * math.sqrt(hour - 1)
        spread = min(max(spread, SPREAD_FLOOR), SPREAD_CAP)
        median = print1 * median_ratio
        quantiles = []
        previous = 0.0
        for z in Z:
            q = round(median * math.exp(z * spread), 2)
            q = min(max(q, previous), MAX_VIEWERS)
            if q <= 0:
                q = previous if previous > 0 else 0.01
            quantiles.append(q)
            previous = q
        rows.append({"hour": hour, "q": quantiles})
    return {"hours": rows}


def main(argv=None):
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    try:
        names = sorted(n for n in os.listdir(input_dir) if n.endswith(".in"))
    except OSError as exc:
        print("crowdline: cannot list input dir %s: %s" % (input_dir, exc),
              file=sys.stderr)
        return 1
    os.makedirs(output_dir, exist_ok=True)
    for name in names:
        case_id = name[: -len(".in")]
        with open(os.path.join(input_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        forecast = forecast_case(case)
        out_path = os.path.join(output_dir, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(forecast, fh, separators=(",", ":"))
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
