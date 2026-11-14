import logging
import sys
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import rasterio
from rasterio.errors import RasterioError

from .terrain import ELEVATION_MAP, GLOBAL_ELEVATION_MAP, TERRAIN_MAP

NASA_DATA_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp"
NASA_GLOBAL_DATA_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_PA"
CHUNK_SIZE = 1024 * 1024
logger = logging.getLogger("uvicorn.error").getChild(__name__)


def ensure_terrain_maps() -> None:
    rasters = (
        (TERRAIN_MAP, NASA_DATA_URL),
        (ELEVATION_MAP, NASA_DATA_URL),
        (GLOBAL_ELEVATION_MAP, NASA_GLOBAL_DATA_URL),
    )

    for destination, base_url in rasters:
        if destination.is_file():
            continue

        try:
            _download_map(destination, f"{base_url}/{destination.name}")
        except (OSError, HTTPException, RasterioError) as error:
            logger.warning("[raster_download.py] Could not download %s. Starting without it. The next startup will retry. %s", destination.name, error,)


def _download_map(destination: Path, url: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    show_progress = sys.stderr.isatty()
    logger.info("Downloading %s", destination.name)

    try:
        with urlopen(url, timeout=30) as response:
            if response.status != 200:
                raise OSError(f"[raster_download.py] Expected HTTP 200, got {response.status}")

            content_length = response.headers.get("Content-Length", "")
            total_bytes = int(content_length) if content_length.isdecimal() else None
            received_bytes = 0

            with NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as output:
                temporary_path = Path(output.name)

                while chunk := response.read(CHUNK_SIZE):
                    output.write(chunk)
                    received_bytes += len(chunk)

                    if show_progress:
                        progress = f"{received_bytes / CHUNK_SIZE:.1f} MiB"
                        if total_bytes:
                            percent = min(100, received_bytes * 100 // total_bytes)
                            filled = percent // 5
                            bar = "#" * filled + "-" * (20 - filled)
                            progress = f"[{bar}] {percent:3d}%"
                        print(f"\rDownloading {destination.name} {progress}", end="", file=sys.stderr, flush=True,)

        if total_bytes is not None and received_bytes != total_bytes:
            raise OSError(f"[raster_download.py] Incomplete download ({received_bytes} of {total_bytes} bytes)")

        with rasterio.open(temporary_path) as raster:
            if raster.driver != "GTiff" or raster.count < 1:
                raise OSError("[raster_download.py] Downloaded file is not a GeoTIFF with a raster band!")

            if destination == GLOBAL_ELEVATION_MAP:
                if (raster.width, raster.height) != (360 * 64, 180 * 64):
                    raise OSError("[raster_download.py] Unexpected dimensions for the 64 ppd LOLA global grid!")
            elif raster.crs is None or not raster.crs.is_projected:
                raise OSError("[raster_download.py] Downloaded polar GeoTIFF is missing a projected CRS!")

        if not destination.is_file():
            temporary_path.replace(destination)
        logger.info("Raster ready at %s", destination)
    finally:
        if show_progress:
            print(file=sys.stderr)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)