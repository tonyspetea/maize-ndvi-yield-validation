"""Shared settings for the crop monitoring project.

Change these to match your study area. Everything else reads from here.
"""
import math

# Outlines of the maize plots, as (longitude, latitude) pairs drawn on geojson.io.
# The real outlines used for the results in this repository are kept private in config_private.py
# (not uploaded). Without that file, this made-up example rectangle is used so the code still runs.
# To use your own plot, create config_private.py containing your own POLYGONS = [...] list.
try:
    from config_private import POLYGONS
except ImportError:
    POLYGONS = [
        [
            (35.0000, 1.0200),
            (35.0010, 1.0200),
            (35.0010, 1.0210),
            (35.0000, 1.0210),
            (35.0000, 1.0200),
        ],
    ]

# Search box for the satellite scenes: the bounding box of all sections plus ~10 m padding.
_PAD = 10  # metres
_lons = [p[0] for ring in POLYGONS for p in ring]
_lats = [p[1] for ring in POLYGONS for p in ring]
_dlat = _PAD / 110574
_dlon = _PAD / (111320 * math.cos(math.radians(sum(_lats) / len(_lats))))
BBOX = (min(_lons) - _dlon, min(_lats) - _dlat, max(_lons) + _dlon, max(_lats) + _dlat)

# Centre point used for the weather download
LON = (BBOX[0] + BBOX[2]) / 2
LAT = (BBOX[1] + BBOX[3]) / 2

# Period for the weather chart and single run (steps 01 to 03):
# March 2025 to Feb 2026 = long rains (plant Mar, harvest Aug) + short rains (plant Oct, harvest Feb)
START = "2025-03-01"
END = "2026-02-28"

# Satellite scenes with more cloud than this are skipped
MAX_CLOUD = 40  # percent

# Minimum clean 10 m pixels inside the plot for a scene to count.
# The three sections together cover about 48 pixels, so 15 means "about a third is cloud-free".
MIN_PIXELS = 15

# Two crop seasons per year on this farm.
#   L = long rains:  plant March,   harvest August   (same calendar year)
#   S = short rains: plant October, harvest February (ends in the NEXT year)
# A season id is the year it STARTS plus the letter: 2024S = Oct 2024 to Feb 2025.
SEASONS = {
    "L": {"start": "03-01", "end": "08-31", "end_year_offset": 0},
    "S": {"start": "10-01", "end": "02-28", "end_year_offset": 1},
}


def season_window(season_id: str):
    """('2024S') -> ('2024-10-01', '2025-02-28')"""
    year, kind = int(season_id[:4]), season_id[-1]
    cfg = SEASONS[kind]
    return f"{year}-{cfg['start']}", f"{year + cfg['end_year_offset']}-{cfg['end']}"


# Seasons to download in step 04: every finished season since the first yield record (2021L).
# 2026S was only planted in October 2026, so it is not included yet.
SEASON_IDS = sorted([f"{y}L" for y in range(2021, 2027)] + [f"{y}S" for y in range(2021, 2026)])

# Output folders
DATA_DIR = "data"
OUT_DIR = "outputs"
