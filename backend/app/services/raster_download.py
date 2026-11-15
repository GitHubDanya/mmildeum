import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB
RANGE_WORKERS = 4
MIN_SPLIT_SIZE = 32 * 1024 * 1024  # 32 MiB
REQUEST_TIMEOUT = 30

GLOBAL_64PPD_MAPS = {GLOBAL_ELEVATION_MAP, GLOBAL_EQC_ELEVATION_MAP}
ALL_RASTER_MAPS = (
    ELEVATION_MAP,
    ROUGHNESS_CLASS_MAP,
    GLOBAL_ELEVATION_MAP,
    GLOBAL_EQC_ELEVATION_MAP,
    LOLA_ROUGHNESS_MAP,
)

logger = logging.getLogger("uvicorn.error").getChild(__name__)

_STOP_EVENT = threading.Event()
_ACTIVE_RESPONSES: set = set()
_RESPONSES_LOCK = threading.Lock()


def _abort_downloads() -> None:
    """Signal all worker threads to stop and immediately close active sockets."""
    _STOP_EVENT.set()
    with _RESPONSES_LOCK:
        for resp in list(_ACTIVE_RESPONSES):
            try:
                sock = getattr(getattr(resp.fp, "raw", None), "_sock", None)
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                resp.close()
            except OSError:
                pass


def _tracked_urlopen(req_or_url, timeout: int = REQUEST_TIMEOUT):
    if _STOP_EVENT.is_set():
        raise InterruptedError("Download cancelled")
    resp = urlopen(req_or_url, timeout=timeout)
    with _RESPONSES_LOCK:
        if _STOP_EVENT.is_set():
            resp.close()
            raise InterruptedError("Download cancelled")
        _ACTIVE_RESPONSES.add(resp)
    return resp


def _release_response(resp) -> None:
    with _RESPONSES_LOCK:
        _ACTIVE_RESPONSES.discard(resp)


def ensure_terrain_maps() -> None:
    _STOP_EVENT.clear()
    base_url = RASTER_SERVER_URL.rstrip("/")
    pending: list[Path] = []

    for destination in ALL_RASTER_MAPS:
        if _has_valid_map(destination):
            continue
        if destination.exists():
            logger.warning("Existing %s is corrupt or incomplete; re-downloading.", destination.name)
        pending.append(destination)

    if not pending:
        return

    pool = ThreadPoolExecutor(max_workers=len(pending))
    futures = {
        pool.submit(_download_map, dest, f"{base_url}/{dest.name}"): dest
        for dest in pending
    }

    try:
        for future in as_completed(futures):
            dest = futures[future]
            try:
                future.result()
            except (OSError, HTTPException, RasterioError) as e:
                if _STOP_EVENT.is_set() or isinstance(e, InterruptedError):
                    return
                logger.warning(
                    "Could not download %s. Starting without it. The next startup will retry. %s",
                    dest.name,
                    e,
                )
    except KeyboardInterrupt:
        logger.info("Download interrupted by user; cleaning up...")
        _abort_downloads()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


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


def _make_progress_reporter(filename: str, total_bytes: int | None):
    lock = threading.Lock()
    received = 0
    last_log = time.monotonic()

    def report(delta: int) -> None:
        nonlocal received, last_log
        with lock:
            received += delta
            now = time.monotonic()
            if now - last_log < 2.0:
                return
            last_log = now
            mib_done = received / (1024 * 1024)
            if total_bytes:
                mib_total = total_bytes / (1024 * 1024)
                pct = min(100, received * 100 // total_bytes)
                logger.info("Downloading %s: %d%% (%.1f / %.1f MiB)", filename, pct, mib_done, mib_total)
            else:
                logger.info("Downloading %s: %.1f MiB", filename, mib_done)

    return report


def _probe_file(url: str) -> tuple[int | None, bool]:
    try:
        resp = _tracked_urlopen(Request(url, method="HEAD"))
        try:
            if resp.status != 200:
                raise OSError(f"Expected HTTP 200, got {resp.status}")
            content_length = resp.headers.get("Content-Length", "")
            total_bytes = int(content_length) if content_length.isdecimal() else None
            supports_ranges = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
            return total_bytes, supports_ranges
        finally:
            _release_response(resp)
            resp.close()
    except HTTPError as e:
        if e.code == 405:
            return None, False
        raise


def _download_range(url: str, temp_path: Path, start: int, end: int, report_progress) -> int:
    req = Request(url, headers={"Range": f"bytes={start}-{end}"})
    downloaded = 0
    resp = _tracked_urlopen(req)
    try:
        if resp.status != 206:
            raise OSError(f"Expected HTTP 206 for range request, got {resp.status}")
        with temp_path.open("r+b") as output:
            output.seek(start)
            while not _STOP_EVENT.is_set():
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                n = len(chunk)
                downloaded += n
                report_progress(n)
        if _STOP_EVENT.is_set():
            raise InterruptedError("Download cancelled")
        return downloaded
    finally:
        _release_response(resp)
        resp.close()


def _download_single_stream(url: str, temp_path: Path, report_progress) -> tuple[int, int | None]:
    downloaded = 0
    resp = _tracked_urlopen(url)
    try:
        if resp.status != 200:
            raise OSError(f"Expected HTTP 200, got {resp.status}")
        content_length = resp.headers.get("Content-Length", "")
        total_bytes = int(content_length) if content_length.isdecimal() else None
        with temp_path.open("wb") as output:
            while not _STOP_EVENT.is_set():
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                n = len(chunk)
                downloaded += n
                report_progress(n)
        if _STOP_EVENT.is_set():
            raise InterruptedError("Download cancelled")
        return downloaded, total_bytes
    finally:
        _release_response(resp)
        resp.close()


def _download_map(destination: Path, url: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    logger.info("Downloading %s from %s", destination.name, url)

    try:
        total_bytes, supports_ranges = _probe_file(url)
        report_progress = _make_progress_reporter(destination.name, total_bytes)

        with NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as output:
            temporary_path = Path(output.name)
            if total_bytes:
                output.truncate(total_bytes)

        if total_bytes and supports_ranges and total_bytes >= MIN_SPLIT_SIZE:
            part_size = (total_bytes + RANGE_WORKERS - 1) // RANGE_WORKERS
            ranges = [
                (i * part_size, min(total_bytes - 1, (i + 1) * part_size - 1))
                for i in range(RANGE_WORKERS)
                if i * part_size < total_bytes
            ]
            range_pool = ThreadPoolExecutor(max_workers=len(ranges))
            try:
                range_futures = [
                    range_pool.submit(_download_range, url, temporary_path, start, end, report_progress)
                    for start, end in ranges
                ]
                received_bytes = sum(f.result() for f in as_completed(range_futures))
            finally:
                range_pool.shutdown(wait=False, cancel_futures=True)
        else:
            received_bytes, stream_total = _download_single_stream(url, temporary_path, report_progress)
            if total_bytes is None:
                total_bytes = stream_total

        if _STOP_EVENT.is_set():
            raise InterruptedError("Download cancelled")

        if total_bytes is not None and received_bytes != total_bytes:
            raise OSError(f"Incomplete download ({received_bytes} of {total_bytes} bytes)")

        _validate_raster_file(temporary_path, destination)
        temporary_path.replace(destination)
        logger.info("Raster ready at %s", destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)