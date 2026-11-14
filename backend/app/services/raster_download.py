import logging
import sys
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
import rasterio
from rasterio.errors import RasterioError
from .terrain import ELEVATION_MAP, TERRAIN_MAP

NASA_DATA_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp"
CHUNK_SIZE = 1024 * 1024
logger = logging.getLogger("uvicorn.error").getChild(__name__)


def ensure_terrain_maps() -> None:
    """
    Download any missing LOLA terrain and elevation maps from NASA PGDA.
    Maps already on disk are skipped. A failed download is logged as a warning instead of raised,
    so the server starts without that map and the download is retried on the next startup.
    """
    for destination in (TERRAIN_MAP, ELEVATION_MAP):
        if destination.is_file():
            continue

        try:
            _download_map(destination)
        except (OSError, HTTPException, RasterioError) as e:
            logger.warning("[raster_download.py] Could not download %s. Starting without it. The next startup will retry. %s!", destination.name, e)


def _download_map(destination: Path) -> None:
    """
    Download one LOLA GeoTIFF from NASA PGDA and move it to its destination once it is validated.
    The file is streamed in 1 MiB chunks to a temporary .part file next to the destination, with a
    progress bar on stderr when stderr is a terminal. The temporary file replaces the destination
    only if its size matches Content-Length and it opens as a projected GeoTIFF with at least one band;
    otherwise it is deleted.
    :param destination: Local path for the map; its file name is also the file requested from NASA PGDA
    :type destination: Path
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{NASA_DATA_URL}/{destination.name}"
    temporary_path = None
    show_progress = sys.stderr.isatty()
    logger.info("Downloading %s", destination.name)

    try:
        with urlopen(url, timeout=30) as response:
            if response.status != 200:
                raise OSError(f"[raster_download.py] Expected HTTP 200, got {response.status}!")
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
                            progress = f"[{bar} {percent:3d}%]"
                            print(f"\rDownloading {destination.name} {progress}", end="", file=sys.stderr, flush=True)
        if total_bytes is not None and received_bytes != total_bytes:
            raise OSError(f"[raster_download.py] Incomplete download ({received_bytes} of {total_bytes} bytes)!")
        with rasterio.open(temporary_path) as raster:
            if raster.driver != "GTiff" or raster.count < 1:
                raise OSError("[raster_download.py] Downloaded file is not a GeoTIFF with a raster band!")
            if raster.crs is None or not raster.crs.is_projected:
                raise OSError("[raster_download.py] Downloaded GeoTIFF is missing a projected CRS!")

        if not destination.is_file():
            temporary_path.replace(destination)
        logger.info("Raster ready at %s", destination)
    finally:
        if show_progress:
            print(file=sys.stderr)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)