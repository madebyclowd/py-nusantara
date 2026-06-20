import math
import json
import logging
import heapq
import functools
from typing import Any, List, Optional

logger = logging.getLogger("py_nusantara")

# Try to import shapely for C-optimized boundary checks
try:
    import shapely.geometry
    import shapely.prepared
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


@functools.lru_cache(maxsize=10000)
def _get_cached_geometry(boundary_str: str) -> Optional[Any]:
    """Parse geometry and cache it.
    
    If Shapely is available, returns a prepared Shapely geometry.
    Otherwise, returns a tuple of (coords, (min_lat, min_lon, max_lat, max_lon)).
    """
    try:
        coords = json.loads(boundary_str)
    except Exception as e:
        logger.debug(f"Failed to parse boundary JSON: {e}")
        return None

    if not isinstance(coords, list) or not coords:
        return None

    if SHAPELY_AVAILABLE:
        try:
            depth = _get_array_depth(coords)
            if depth == 3:
                # Single Polygon (coords[0] is exterior, coords[1:] is interior rings)
                poly = shapely.geometry.Polygon(coords[0], coords[1:])
            elif depth == 4:
                # MultiPolygon (list of polygons)
                polys = []
                for p in coords:
                    if len(p) > 0:
                        polys.append(shapely.geometry.Polygon(p[0], p[1:]))
                poly = shapely.geometry.MultiPolygon(polys)
            else:
                return None
            return shapely.prepared.prep(poly)
        except Exception as e:
            logger.debug(f"Failed to build Shapely geometry: {e}")
            # Fall back to pure Python path if Shapely fails
            pass

    # Fallback/default pure Python path
    pts = _extract_points(coords)
    if not pts:
        return None

    lats = [pt[0] for pt in pts]
    lons = [pt[1] for pt in pts]
    min_lat = min(lats)
    max_lat = max(lats)
    min_lon = min(lons)
    max_lon = max(lons)

    return coords, (min_lat, min_lon, max_lat, max_lon)


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

    parsed = _get_cached_geometry(boundary_str)
    if not parsed:
        return False

    if SHAPELY_AVAILABLE and not isinstance(parsed, tuple):
        try:
            pt = shapely.geometry.Point(lat, lon)
            return parsed.contains(pt)
        except Exception as e:
            logger.debug(f"Shapely point check failed: {e}")
            return False

    # Pure Python path
    coords, (min_lat, min_lon, max_lat, max_lon) = parsed

    # 1. Quick bounding box (AABB) check
    if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
        return False

    # 2. Ray-casting algorithm
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


def latlon_to_3d(lat: float, lon: float) -> tuple[float, float, float]:
    """Convert latitude and longitude (in degrees) to 3D Cartesian coordinates on unit sphere."""
    rad_lat = math.radians(lat)
    rad_lon = math.radians(lon)
    x = math.cos(rad_lat) * math.cos(rad_lon)
    y = math.cos(rad_lat) * math.sin(rad_lon)
    z = math.sin(rad_lat)
    return (x, y, z)


class KDNode:
    """A node in the 3D KD-Tree."""
    def __init__(self, point: tuple[float, float, float], item: Any, axis: int, left=None, right=None):
        self.point = point   # (x, y, z)
        self.item = item     # The record/object associated with this point
        self.axis = axis
        self.left = left
        self.right = right


class KDTree:
    """A 3D KD-Tree for querying spatial coordinates on a unit sphere."""
    def __init__(self, items: list[Any]):
        """Build a 3D KD-Tree from a list of records.

        Each item must have 'latitude' and 'longitude' attributes.
        """
        valid_items = []
        for item in items:
            lat = getattr(item, "latitude", None)
            lon = getattr(item, "longitude", None)
            if lat is not None and lon is not None:
                try:
                    pt_3d = latlon_to_3d(float(lat), float(lon))
                    valid_items.append((pt_3d, item))
                except (ValueError, TypeError):
                    pass
        self.root = self._build(valid_items, 0)

    def _build(self, points: list[tuple[tuple[float, float, float], Any]], depth: int) -> Optional[KDNode]:
        if not points:
            return None
        axis = depth % 3
        points.sort(key=lambda x: x[0][axis])
        median_idx = len(points) // 2
        pt_3d, item = points[median_idx]
        return KDNode(
            point=pt_3d,
            item=item,
            axis=axis,
            left=self._build(points[:median_idx], depth + 1),
            right=self._build(points[median_idx + 1:], depth + 1)
        )

    def query_radius(self, query_pt_3d: tuple[float, float, float], radius_3d: float) -> list[tuple[float, Any]]:
        """Find all nodes within the given 3D Euclidean distance (radius_3d).

        Returns a list of tuples: (distance_3d, item).
        """
        results = []
        self._query_radius_rec(self.root, query_pt_3d, radius_3d, results)
        return results

    def _query_radius_rec(self, node: Optional[KDNode], query: tuple[float, float, float], r: float, results: list):
        if node is None:
            return
        dist_sq = sum((q - n) ** 2 for q, n in zip(query, node.point))
        dist = math.sqrt(dist_sq)
        if dist <= r:
            results.append((dist, node.item))
        axis = node.axis
        axis_dist = query[axis] - node.point[axis]
        if axis_dist < 0:
            self._query_radius_rec(node.left, query, r, results)
            if abs(axis_dist) < r:
                self._query_radius_rec(node.right, query, r, results)
        else:
            self._query_radius_rec(node.right, query, r, results)
            if abs(axis_dist) < r:
                self._query_radius_rec(node.left, query, r, results)

    def query_knn(self, query_pt_3d: tuple[float, float, float], k: int) -> list[tuple[float, Any]]:
        """Find the K nearest neighbors to the query point.

        Returns a list of tuples: (distance_3d, item), sorted by distance ascending.
        """
        if k <= 0 or self.root is None:
            return []
        # Max-heap to store the k closest points.
        # Elements are: (-distance_3d, id(item), item) to avoid comparing items directly.
        heap = []
        self._query_knn_rec(self.root, query_pt_3d, k, heap)
        results = [(-dist, item) for dist, _, item in heap]
        results.sort(key=lambda x: x[0])
        return results

    def _query_knn_rec(self, node: Optional[KDNode], query: tuple[float, float, float], k: int, heap: list):
        if node is None:
            return
        dist_sq = sum((q - n) ** 2 for q, n in zip(query, node.point))
        dist = math.sqrt(dist_sq)
        if len(heap) < k:
            heapq.heappush(heap, (-dist, id(node.item), node.item))
        else:
            worst_dist = -heap[0][0]
            if dist < worst_dist:
                heapq.heapreplace(heap, (-dist, id(node.item), node.item))
        axis = node.axis
        axis_dist = query[axis] - node.point[axis]
        if axis_dist < 0:
            closer_child = node.left
            farther_child = node.right
        else:
            closer_child = node.right
            farther_child = node.left
        self._query_knn_rec(closer_child, query, k, heap)
        worst_dist = -heap[0][0] if len(heap) == k else float("inf")
        if abs(axis_dist) < worst_dist:
            self._query_knn_rec(farther_child, query, k, heap)


def swap_lat_lon(coords: Any) -> Any:
    """Recursively swap [latitude, longitude] arrays to [longitude, latitude] for GeoJSON."""
    if isinstance(coords, list):
        if len(coords) == 2 and not isinstance(coords[0], list):
            return [coords[1], coords[0]]
        return [swap_lat_lon(c) for c in coords]
    return coords


def parse_wkt(wkt_str: str) -> Optional[dict[str, Any]]:
    """Parse POLYGON and MULTIPOLYGON WKT strings into GeoJSON geometry structures."""
    import re
    wkt_str = wkt_str.strip().upper()
    if wkt_str.startswith("POLYGON"):
        rings_str = re.findall(r"\(([^()]+)\)", wkt_str)
        rings = []
        for r_str in rings_str:
            coords = []
            for pt in r_str.split(","):
                parts = pt.strip().split()
                if len(parts) >= 2:
                    try:
                        coords.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        pass
            if coords:
                rings.append(coords)
        if rings:
            return {"type": "Polygon", "coordinates": rings}
    elif wkt_str.startswith("MULTIPOLYGON"):
        poly_matches = re.findall(r"\(\(([^()]+(?:\)\s*,\s*\([^()]+)*)\)\)", wkt_str)
        polygons = []
        for p_str in poly_matches:
            rings_str = re.findall(r"\(([^()]+)\)", f"({p_str})")
            rings = []
            for r_str in rings_str:
                coords = []
                for pt in r_str.split(","):
                    parts = pt.strip().split()
                    if len(parts) >= 2:
                        try:
                            coords.append([float(parts[0]), float(parts[1])])
                        except ValueError:
                            pass
                if coords:
                    rings.append(coords)
            if rings:
                polygons.append(rings)
        if polygons:
            return {"type": "MultiPolygon", "coordinates": polygons}
    return None


def parse_boundary_to_geojson_geometry(boundary_val: Any) -> Optional[dict[str, Any]]:
    """Parse boundary value (JSON coordinate string, WKT string, list, or GeoAlchemy2 element) into GeoJSON."""
    if not boundary_val:
        return None

    # Check if it is a GeoAlchemy2 SpatialElement / WKBElement / WKTElement
    cls_name = boundary_val.__class__.__name__
    if cls_name in ("WKBElement", "WKTElement", "SpatialElement"):
        try:
            from geoalchemy2.shape import to_shape
            import shapely.geometry
            shape = to_shape(boundary_val)
            return shapely.geometry.mapping(shape)
        except Exception:
            if hasattr(boundary_val, "data") and isinstance(boundary_val.data, str):
                boundary_val = boundary_val.data
            elif hasattr(boundary_val, "desc") and isinstance(boundary_val.desc, str):
                # We can try reading from desc (WKB hex) using shapely directly
                try:
                    import shapely.wkb
                    shape = shapely.wkb.loads(bytes.fromhex(boundary_val.desc))
                    return shapely.geometry.mapping(shape)
                except Exception:
                    pass

    if isinstance(boundary_val, str):
        boundary_val = boundary_val.strip()
        if boundary_val.startswith("["):
            try:
                coords = json.loads(boundary_val)
                depth = _get_array_depth(coords)
                geom_type = "Polygon" if depth == 3 else "MultiPolygon"
                swapped = swap_lat_lon(coords)
                return {"type": geom_type, "coordinates": swapped}
            except Exception:
                return None
        elif boundary_val.upper().startswith(("POLYGON", "MULTIPOLYGON")):
            return parse_wkt(boundary_val)

    if isinstance(boundary_val, list):
        depth = _get_array_depth(boundary_val)
        geom_type = "Polygon" if depth == 3 else "MultiPolygon"
        swapped = swap_lat_lon(boundary_val)
        return {"type": geom_type, "coordinates": swapped}
    return None


def _longitude_overlap(b_min_lon: float, b_max_lon: float, min_lon: float, max_lon: float) -> bool:
    """Helper to check if a candidate longitude range [b_min_lon, b_max_lon] overlaps
    with a query longitude range [min_lon, max_lon], supporting antimeridian wrap-around.
    """
    if min_lon <= max_lon:
        return not (b_max_lon < min_lon or b_min_lon > max_lon)
    else:
        # Crosses antimeridian: query region is [min_lon, 180] U [-180, max_lon]
        return not (b_max_lon < min_lon or b_min_lon > 180.0) or not (b_max_lon < -180.0 or b_min_lon > max_lon)


def _is_lon_in_bounds(lon: float, min_lon: float, max_lon: float) -> bool:
    """Helper to check if a point longitude is within the range, supporting antimeridian."""
    if min_lon <= max_lon:
        return min_lon <= lon <= max_lon
    else:
        return lon >= min_lon or lon <= max_lon


def _is_boundary_in_bbox(
    boundary_val: Any,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> bool:
    """Helper to check if a geographic boundary intersects a bounding box.
    
    Coordinates are automatically identified as latitude/longitude based on typical Indonesian bounds.
    """
    if not boundary_val:
        return False

    # Check if it is a GeoAlchemy2 SpatialElement / WKBElement / WKTElement
    cls_name = boundary_val.__class__.__name__
    if cls_name in ("WKBElement", "WKTElement", "SpatialElement"):
        try:
            from geoalchemy2.shape import to_shape
            import shapely.geometry
            shape = to_shape(boundary_val)
            if min_lon <= max_lon:
                bbox_poly = shapely.geometry.box(min_lon, min_lat, max_lon, max_lat)
                return shape.intersects(bbox_poly)
            else:
                bbox_poly1 = shapely.geometry.box(min_lon, min_lat, 180.0, max_lat)
                bbox_poly2 = shapely.geometry.box(-180.0, min_lat, max_lon, max_lat)
                return shape.intersects(bbox_poly1) or shape.intersects(bbox_poly2)
        except Exception:
            if hasattr(boundary_val, "data") and isinstance(boundary_val.data, str):
                boundary_val = boundary_val.data
            elif hasattr(boundary_val, "desc") and isinstance(boundary_val.desc, str):
                try:
                    import shapely.wkb
                    shape = shapely.wkb.loads(bytes.fromhex(boundary_val.desc))
                    if min_lon <= max_lon:
                        bbox_poly = shapely.geometry.box(min_lon, min_lat, max_lon, max_lat)
                        return shape.intersects(bbox_poly)
                    else:
                        bbox_poly1 = shapely.geometry.box(min_lon, min_lat, 180.0, max_lat)
                        bbox_poly2 = shapely.geometry.box(-180.0, min_lat, max_lon, max_lat)
                        return shape.intersects(bbox_poly1) or shape.intersects(bbox_poly2)
                except Exception:
                    pass

    coords = None
    if isinstance(boundary_val, str):
        boundary_val = boundary_val.strip()
        if boundary_val.startswith("["):
            try:
                coords = json.loads(boundary_val)
            except Exception:
                return False
        elif boundary_val.upper().startswith(("POLYGON", "MULTIPOLYGON")):
            geom = parse_wkt(boundary_val)
            if geom and "coordinates" in geom:
                coords = geom["coordinates"]
    elif isinstance(boundary_val, list):
        coords = boundary_val

    if not coords:
        return False

    pts = _extract_points(coords)
    if not pts:
        return False

    # Identify lat/lon coordinates robustly for Indonesian spatial range
    # Indonesia: lat in [-12, 10], lon in [90, 150]
    lats = []
    lons = []
    for pt in pts:
        if len(pt) < 2:
            continue
        val0, val1 = pt[0], pt[1]
        # Heuristic: longitude is always > 80, latitude is < 20 in Indonesia
        if abs(val0) < 20.0 and val1 > 80.0:
            lats.append(val0)
            lons.append(val1)
        elif abs(val1) < 20.0 and val0 > 80.0:
            lats.append(val1)
            lons.append(val0)
        else:
            # Fallback
            lats.append(val0)
            lons.append(val1)

    if not lats or not lons:
        return False

    b_min_lat = min(lats)
    b_max_lat = max(lats)
    b_min_lon = min(lons)
    b_max_lon = max(lons)

    # Check for latitude overlap
    lat_overlap = not (b_max_lat < min_lat or b_min_lat > max_lat)
    
    # Check for longitude overlap (with antimeridian handling)
    lon_overlap = _longitude_overlap(b_min_lon, b_max_lon, min_lon, max_lon)

    return lat_overlap and lon_overlap


def _extract_points(arr: Any) -> List[List[float]]:
    """Recursively extract all coordinate points [x, y] from nested lists."""
    if not isinstance(arr, list):
        return []
    if len(arr) == 2 and not isinstance(arr[0], list):
        try:
            return [[float(arr[0]), float(arr[1])]]
        except (ValueError, TypeError):
            return []
    res = []
    for item in arr:
        res.extend(_extract_points(item))
    return res
