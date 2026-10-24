"""Step 2: build an NDVI time series from Sentinel-2 satellite images.

Source: Sentinel-2 L2A on Microsoft Planetary Computer (free, no account
needed for reading). We search for scenes over the plot, read only the small
window we need (not whole 100 km tiles), keep only pixels whose centre is inside
the section outlines (config.POLYGONS), remove clouds using the scene classification
layer (SCL), and compute the mean NDVI per date.

NDVI = (NIR - Red) / (NIR + Red)   -> Sentinel-2 bands B08 and B04
Healthy green crops give high NDVI (about 0.6 to 0.9); bare soil is low.

Run:  python 02_ndvi.py        (this can take 5 to 15 minutes)
Output: data/ndvi_timeseries.csv
"""
import os
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds
import planetary_computer
from pystac_client import Client
import config

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# SCL classes to treat as unusable: no data, shadows, cloud (med/high),
# thin cirrus, snow
BAD_SCL = {0, 1, 3, 8, 9, 10, 11}


def read_band(href: str, bbox_wgs84, like_shape=None):
    """Read a window of one band covering bbox.

    Returns (array, window_transform, crs). If like_shape is given the band is
    resampled to that shape, so bands with different resolution line up.
    """
    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *bbox_wgs84)
        win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win, out_shape=like_shape).astype("float32")
        return arr, src.window_transform(win), src.crs


def inside_plot(crs, transform, shape, polygons=None) -> np.ndarray:
    """True for pixels whose centre is inside any of the maize section outlines."""
    polygons = polygons if polygons is not None else config.POLYGONS
    geoms = [
        transform_geom("EPSG:4326", crs, {"type": "Polygon", "coordinates": [[list(p) for p in ring]]})
        for ring in polygons
    ]
    return geometry_mask(geoms, out_shape=shape, transform=transform, invert=True)


def scene_ndvi(item):
    """Return (mean cloud-free NDVI, clean pixel count) for one scene, or None."""
    signed = planetary_computer.sign(item)
    red, transform, crs = read_band(signed.assets["B04"].href, config.BBOX)
    nir, _, _ = read_band(signed.assets["B08"].href, config.BBOX, like_shape=red.shape)
    scl, _, _ = read_band(signed.assets["SCL"].href, config.BBOX, like_shape=red.shape)

    # Newer Sentinel-2 scenes have a +1000 offset in the digital numbers
    def to_reflectance(asset_key, arr):
        band_info = signed.assets[asset_key].extra_fields.get("raster:bands", [{}])[0]
        scale = band_info.get("scale", 0.0001)
        offset = band_info.get("offset", 0.0)
        return arr * scale + offset

    red = to_reflectance("B04", red)
    nir = to_reflectance("B08", nir)

    plot = inside_plot(crs, transform, red.shape)
    good = plot & ~np.isin(scl, list(BAD_SCL)) & (red > 0) & (nir > 0)
    if good.sum() < config.MIN_PIXELS:  # too few clean pixels inside the plot
        return None
    ndvi = (nir[good] - red[good]) / (nir[good] + red[good])
    return float(np.nanmean(ndvi)), int(good.sum())  # (value, pixel count)


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    catalog = Client.open(STAC_URL)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=config.BBOX,
        datetime=f"{config.START}/{config.END}",
        query={"eo:cloud_cover": {"lt": config.MAX_CLOUD}},
    )
    items = sorted(search.items(), key=lambda i: i.datetime)
    print(f"Found {len(items)} scenes under {config.MAX_CLOUD}% cloud.")

    rows = []
    for n, item in enumerate(items, 1):
        try:
            result = scene_ndvi(item)
        except Exception as e:  # keep going if one scene fails
            print(f"  [{n}/{len(items)}] {item.datetime.date()} failed: {e}")
            continue
        if result is None:
            print(f"  [{n}/{len(items)}] {item.datetime.date()} skipped (cloudy over the plot)")
            continue
        ndvi, npix = result
        rows.append({"date": item.datetime.date(), "ndvi": round(ndvi, 4), "clean_pixels": npix})
        print(f"  [{n}/{len(items)}] {item.datetime.date()}  NDVI={ndvi:.3f}  ({npix} pixels)")

    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df.to_csv(f"{config.DATA_DIR}/ndvi_timeseries.csv", index=False)
    print(f"Saved {len(df)} NDVI observations.")


if __name__ == "__main__":
    main()
