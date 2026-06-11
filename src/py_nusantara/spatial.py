import math
import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger("py_nusantara")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    try:
        # Convert decimal degrees to radians
        r_lat1, r_lon1, r_lat2, r_lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = r_lat2 - r_lat1
        dlon = r_lon2 - r_lon1
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(dlon / 2.0) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        r = 6371.0  # Radius of earth in kilometers
        return c * r
    except Exception as e:
        logger.debug(f"Failed to calculate haversine distance: {e}")
        return float("inf")


def is_point_in_boundary(lat: float, lon: float, boundary_str: Optional[str]) -> bool:
    """Check if a coordinate (lat, lon) is inside a GeoJSON Polygon or MultiPolygon boundary string.
    
    Coordinates are assumed to be structured as [latitude, longitude] in the boundary JSON arrays.
    """
    if not boundary_str:
        return False
    try:
        coords = json.loads(boundary_str)
    except Exception as e:
        logger.debug(f"Failed to parse boundary JSON: {e}")
        return False

    if not isinstance(coords, list) or not coords:
        return False

    depth = _get_array_depth(coords)
    if depth == 3:
        # Single Polygon (list of rings)
        return point_in_polygon(lat, lon, coords)
    elif depth == 4:
        # MultiPolygon (list of polygons)
        return any(point_in_polygon(lat, lon, poly) for poly in coords)

    return False


def _get_array_depth(arr: Any) -> int:
    """Calculate the maximum nesting depth of an array/list."""
    if not isinstance(arr, list):
        return 0
    if not arr:
        return 1
    return 1 + max(_get_array_depth(item) for item in arr)


def point_in_polygon(x: float, y: float, polygon: List[List[List[float]]]) -> bool:
    """Jordan curve theorem (ray casting algorithm) to check if point (x, y) is inside polygon.
    
    x: Latitude of query point
    y: Longitude of query point
    polygon: List of rings, where each ring is a list of [lat, lon] coordinates.
    """
    inside = False
    for ring in polygon:
        n = len(ring)
        if n < 3:
            continue
        p1x, p1y = ring[0]
        for i in range(n + 1):
            p2x, p2y = ring[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
    return inside
