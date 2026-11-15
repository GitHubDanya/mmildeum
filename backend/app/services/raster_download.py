import logging
import os
import sys
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import rasterio
from rasterio.errors import RasterioError

from .terrain import (
    ELEVATION_MAP,
    GLOBAL_ELEVATION_MAP,
    GLOBAL_EQC_ELEVATION_MAP,
    LOLA_ROUGHNESS_FILE_SIZE,
    LOLA_ROUGHNESS_MAP,
    ROUGHNESS_CLASS_MAP,
)

RASTER_SERVER_URL = os.getenv("RASTER_SERVER_URL", "http://85.130.207.70:19508")
CHUNK_SIZE = 1024 * 1024

GLOBAL_64PPD_MAPS = {GLOBAL_ELEVATION_MAP, GLOBAL_EQC_ELEVATION_MAP}
ALL_RASTER_MAPS = (
    ELEVATION_MAP,
    ROUGHNESS_CLASS_MAP,
    GLOBAL_ELEVATION_MAP,
    GLOBAL_EQC_ELEVATION_MAP,
    LOLA_ROUGHNESS_MAP,
)

logger = logging.getLogger("uvicorn.error").getChild(__name__)


def ensure_terrain_maps() -> None:
    base_url = RASTER_SERVER_URL.rstrip("/")

    for destination in ALL_RASTER_MAPS:
        try:
            if _has_valid_map(destination):
                continue

            if destination.exists():
                logger.warning("Existing %s is corrupt or incomplete; re-downloading.", destination.name)

            _download_map(destination, f"{base_url}/{destination.name}")
        except (OSError, HTTPException, RasterioError) as e:
            logger.warning(
                "Could not download %s. Starting without it. The next startup will retry. %s",
                destination.name,
                e,
            )


def _has_valid_map(destination: Path) -> bool:
    if not destination.is_file():
        return False
    try:
        _validate_raster_file(destination, destination)
        return True
    except (OSError, RasterioError):
        return False


def _validate_raster_file(file_path: Path, target_map: Path) -> None:
    if target_map == LOLA_ROUGHNESS_MAP:
        if file_path.stat().st_size != LOLA_ROUGHNESS_FILE_SIZE:
            raise OSError("Unexpected byte count for the LOLA roughness grid.")
        return

    with rasterio.open(file_path) as raster:
        if raster.driver != "GTiff" or raster.count < 1:
            raise OSError("File is not a valid GeoTIFF with a raster band.")

        if target_map in GLOBAL_64PPD_MAPS:
            if (raster.width, raster.height) != (360 * 64, 180 * 64):
                raise OSError("Unexpected dimensions for the 64 ppd LOLA global grid.")
        elif raster.crs is None or not raster.crs.is_projected:
            raise OSError("Polar GeoTIFF is missing a projected CRS.")


def _download_map(destination: Path, url: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    show_progress = sys.stderr.isatty()
    logger.info("Downloading %s from %s", destination.name, url)

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
                        print(
                            f"\rDownloading {destination.name} {progress}",
                            end="",
                            file=sys.stderr,
                            flush=True,
                        )

        if total_bytes is not None and received_bytes != total_bytes:
            raise OSError(
                f"[raster_download.py] Incomplete download ({received_bytes} of {total_bytes} bytes)"
            )

        _validate_raster_file(temporary_path, destination)
        temporary_path.replace(destination)
        logger.info("Raster ready at %s", destination)
    finally:
        if show_progress:
            print(file=sys.stderr)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)