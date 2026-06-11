import os
import json
import urllib.request
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from py_nusantara.config import NusantaraConfig
from py_nusantara.manifest import Manifest
from py_nusantara.exceptions import NusantaraError, IntegrityError


def get_default_cache_dir() -> Path:
    """Resolve the default user cache directory for py-nusantara."""
    return Path.home() / ".cache" / "py-nusantara"


def json_to_wkt(json_str: str) -> Optional[str]:
    """Convert raw JSON coordinate array into Well-Known Text (WKT) format.
    
    Coordinates are assumed to be structured as [latitude, longitude] in JSON
    and will be formatted as Longitude Latitude in WKT.
    """
    if not json_str:
        return None

    try:
        coords = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(coords, list) or not coords:
        return None

    # Determine nesting depth to distinguish Polygon vs MultiPolygon
    depth = _get_array_depth(coords)

    if depth == 3:
        # Single Polygon
        return _format_polygon_wkt(coords)
    elif depth == 4:
        # MultiPolygon
        return _format_multipolygon_wkt(coords)

    return None


def _get_array_depth(arr: Any) -> int:
    """Calculate the maximum nesting depth of an array/list."""
    if not isinstance(arr, list):
        return 0
    if not arr:
        return 1
    return 1 + max(_get_array_depth(item) for item in arr)


def _format_polygon_wkt(polygon: List[List[List[float]]]) -> Optional[str]:
    """Format coordinate list as WKT POLYGON."""
    rings = []
    for ring in polygon:
        if not isinstance(ring, list):
            continue
        points = []
        for coord in ring:
            if isinstance(coord, list) and len(coord) >= 2:
                # Swap coordinates: JSON is [lat, lon], WKT requires "lon lat"
                points.append(f"{coord[1]} {coord[0]}")
        
        if points:
            # Ensure the ring is closed
            if points[0] != points[-1]:
                points.append(points[0])
            # Degenerate rings (fewer than 4 points) are skipped
            if len(points) < 4:
                continue
            rings.append("(" + ", ".join(points) + ")")

    if not rings:
        return None

    return f"POLYGON({', '.join(rings)})"


def _format_multipolygon_wkt(multipolygon: List[List[List[List[float]]]]) -> Optional[str]:
    """Format coordinate list as WKT MULTIPOLYGON."""
    polygons = []
    for polygon in multipolygon:
        if not isinstance(polygon, list):
            continue
        rings = []
        for ring in polygon:
            if not isinstance(ring, list):
                continue
            points = []
            for coord in ring:
                if isinstance(coord, list) and len(coord) >= 2:
                    points.append(f"{coord[1]} {coord[0]}")
            
            if points:
                if points[0] != points[-1]:
                    points.append(points[0])
                if len(points) < 4:
                    continue
                rings.append("(" + ", ".join(points) + ")")

        if rings:
            polygons.append("(" + ", ".join(rings) + ")")

    if not polygons:
        return None

    return f"MULTIPOLYGON({', '.join(polygons)})"


def download_boundaries(
    levels: Union[str, List[str]] = "all",
    force: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    config: Optional[NusantaraConfig] = None,
    progress_callback: Optional[Any] = None,
) -> List[Path]:
    """Download geographic boundary shapefiles from CDN and verify their checksums.
    
    Args:
        levels: Level(s) to download: 'all' or list containing 'provinces', 'regencies', etc.
        force: If True, redownload and overwrite existing cached boundaries.
        cache_dir: Custom directory to store downloaded files.
        config: Custom NusantaraConfig instance.
        progress_callback: Callback(event_name, filename_or_msg) for logging.
        
    Returns:
        List of resolved boundary file paths in the cache directory.
    """
    cfg = config or NusantaraConfig()
    
    # Resolve Cache Directory
    # We can get local_path from configuration boundaries key, or fallback to default
    boundaries_cfg = cfg._config.get("boundaries", {})
    configured_local = boundaries_cfg.get("local_path")
    
    if cache_dir:
        resolved_cache_dir = Path(cache_dir)
    elif configured_local:
        resolved_cache_dir = Path(configured_local)
    else:
        resolved_cache_dir = get_default_cache_dir()

    resolved_cache_dir.mkdir(parents=True, exist_ok=True)

    # Resolve Levels
    allowed_levels = ["provinces", "regencies", "districts", "villages"]
    if levels == "all":
        target_levels = allowed_levels
    elif isinstance(levels, str):
        target_levels = [levels]
    else:
        target_levels = list(levels)

    for level in target_levels:
        if level not in allowed_levels:
            raise NusantaraError(f"Invalid boundary level: '{level}'. Supported: {allowed_levels}")

    cdn_url = boundaries_cfg.get("cdn_url", "https://github.com/madebyclowd/laravel-nusantara/releases/download").rstrip("/")
    version = boundaries_cfg.get("version") or "v1.1.0"

    downloaded_paths = []

    for level in target_levels:
        if level == "villages":
            # For villages, we have sharded files from villages_11.csv.gz to villages_96.csv.gz
            # Let's resolve the list of filenames to download from Manifest
            village_files = [k for k in Manifest.HASHES.keys() if k.startswith("villages_")]
            for filename in village_files:
                filepath = resolved_cache_dir / filename
                if _resolve_single_file(filename, filepath, cdn_url, version, force, progress_callback):
                    downloaded_paths.append(filepath)
        else:
            filename = f"{level}.csv.gz"
            filepath = resolved_cache_dir / filename
            if _resolve_single_file(filename, filepath, cdn_url, version, force, progress_callback):
                downloaded_paths.append(filepath)

    return downloaded_paths


def _resolve_single_file(
    filename: str,
    filepath: Path,
    cdn_url: str,
    version: str,
    force: bool,
    progress_callback: Optional[Any],
) -> bool:
    """Download and verify a single boundary file, returning True if resolved successfully."""
    # Check if already exists and is valid
    if not force and filepath.exists():
        try:
            Manifest.verify(filepath)
            if progress_callback:
                progress_callback("skip", filename)
            return True
        except IntegrityError:
            # Checksum invalid, will redownload
            pass

    # Build download URL
    url = f"{cdn_url}/{version}/{filename}"
    if progress_callback:
        progress_callback("download_start", filename)

    try:
        temp_filepath = filepath.with_suffix(".tmp")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "py-nusantara-downloader/0.1.0"}
        )
        with urllib.request.urlopen(req) as response, open(temp_filepath, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
        
        # Verify integrity of downloaded temp file
        Manifest.verify(temp_filepath)
        
        # Move to actual location
        if filepath.exists():
            filepath.unlink()
        temp_filepath.rename(filepath)
        
        if progress_callback:
            progress_callback("download_success", filename)
        return True

    except Exception as e:
        if temp_filepath.exists():
            temp_filepath.unlink()
        if progress_callback:
            progress_callback("download_failed", f"{filename}: {str(e)}")
        # Raise for tracked files, ignore if verify_checksum is bypassed (we keep it strict by default)
        raise NusantaraError(f"Failed to download boundary file '{filename}' from {url}: {e}")
