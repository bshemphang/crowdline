# crowdline

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/bshemphang/crowdline/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/bshemphang/crowdline/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

An hour-by-hour Twitch audience forecaster for big game launch days, built
for the make.fun bounty
**"Forecast GTA VI's launch-day Twitch viewers hour by hour"**
(`gta6-twitch-ccu-forecast-01`, $250 pool, 20 places pay).

One hour into the release day, it forecasts how many people will be watching
the game live on Twitch in each of the other 23 hours, as five quantiles an
hour. It runs offline in the sandbox: Python 3.13, standard library only, no
network, deterministic.

## Model

A launch-day audience curve is mostly a shape, not a level. The level comes
from the case's own hour-1 print; the shape comes from the comparables, past
big launches' hourly curves shipped in the case.

For each hour, every comparable contributes the ratio of its hour-h viewers
to its own hour-1 viewers, weighted by how close its scale is to the
target's: mega-launches hold their audience through the night while small
ones fade, so the weight is a Gaussian kernel in log space over the hour-1
prints (bandwidth 1.0 log units). The forecast median is the hour-1 print
times the weighted median ratio, and the spread is the weighted spread of
those ratios in log space, floored at 0.15 and capped at 1.0. Quantiles are
the median times exp(z * spread) at the standard normal quantiles.

## Local evaluation

Leave-one-out over the 38 comparables in the practice case (hold one launch
out, forecast its release day from the other 37, score the mean pinball loss
on the log scale against its actual hours 2-24):

```
model     0.4063
baseline  0.9297   (house persistence baseline, same held-out launches)
```

The model beats the baseline by 56% overall, and in every size bucket:
big launches (hour-1 print >= 100k, the GTA VI-relevant bucket) 0.2149 vs
0.2611, mid 0.3116 vs 0.4091, small 0.8168 vs 2.5719. The house baseline
scores about 0.387 on the four practice cases; the practice cases' own
answers are not in the kit, so that figure is not directly comparable.

## Run it

```sh
KIT=~/workspace/makefun/gta6-twitch-ccu-forecast-01-kit/kit/gta6-twitch-ccu-forecast-01-kit
mkdir -p out && MAKEFUN_INPUT_DIR=$KIT/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Writes `out/p00.out` … `out/p03.out`, one forecast per practice case. Two
runs on the same case produce byte-identical output (verified); all four
cases run in under a second total, well inside the 8-second cap.

## Files

- `main.py` — the forecaster (Python 3.13, standard library only)
- `LICENSE` — MIT

---

<sub>Entered on [make.fun](https://make.fun/?ref=v6wvv0dh&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
