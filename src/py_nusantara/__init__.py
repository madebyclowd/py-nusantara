from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging
import threading

# Initialize package logger
logger = logging.getLogger("py_nusantara")

from py_nusantara.config import NusantaraConfig
from py_nusantara.exceptions import (
    NusantaraError,
    ConfigurationError,
    IntegrityError,
    DataNotFoundError,
    NIKValidationError,
    PostalCodeValidationError,
)
from py_nusantara.cache import NoCache, InMemoryCache, RedisCache
from py_nusantara.records import (
    BaseRecord,
    ProvinceRecord,
    RegencyRecord,
    DistrictRecord,
    VillageRecord,
)
from py_nusantara.reader import NusantaraReader
from py_nusantara.search import NusantaraSearch
from py_nusantara.db import build_models, NusantaraSeeder
from py_nusantara.downloader import download_boundaries as _download_boundaries, json_to_wkt
from py_nusantara.spatial import is_point_in_boundary, haversine_distance, _is_boundary_in_bbox
from py_nusantara.query_adapter import InMemoryQueryAdapter, DatabaseQueryAdapter
from py_nusantara.nik import (
    NIKInfo,
    parse_nik as _parse_nik,
    validate_nik as _validate_nik,
)
from py_nusantara.postal_code import (
    PostalCodeInfo,
    parse_postal_code as _parse_postal_code,
    validate_postal_code as _validate_postal_code,
)
from py_nusantara.utils import (
    clean_region_code,
    format_region_code,
    validate_region_code,
)
from py_nusantara.historical import resolve_legacy_id

__all__ = [
    "Nusantara",
    "NusantaraError",
    "ConfigurationError",
    "IntegrityError",
    "DataNotFoundError",
    "NIKValidationError",
    "NIKInfo",
    "PostalCodeValidationError",
    "PostalCodeInfo",
    "BaseRecord",
    "ProvinceRecord",
    "RegencyRecord",
    "DistrictRecord",
    "VillageRecord",
    "build_models",
    "NusantaraSeeder",
    "download_boundaries",
    "json_to_wkt",
    "seed_boundaries",
    "seed_boundaries_async",
    "provinces",
    "find_province",
    "regencies_of",
    "find_regency",
    "districts_of",
    "find_district",
    "villages_of",
    "find_village",
    "search",
    "clear_cache",
    "find_by_coordinate",
    "provinces_df",
    "regencies_df",
    "districts_df",
    "villages_df",
    "parse_nik",
    "validate_nik",
    "parse_postal_code",
    "validate_postal_code",
    "clean_region_code",
    "format_region_code",
    "validate_region_code",
    "find_nearby",
    "find_knn",
    "find_in_bbox",
    "resolve_legacy_id",
]


class Nusantara:
    """The central access point (Facade) for py-nusantara administrative regions."""

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None, engine=None, session=None) -> None:
        self.config = NusantaraConfig(config_dict)
        self.reader = NusantaraReader(self.config)
        self.searcher = NusantaraSearch(self.config, self.reader)
        
        # Pluggable caching configuration
        if not self.config.cache_enabled:
            self.cache = NoCache()
        elif self.config.redis_url:
            use_pickle = self.config._config.get("cache", {}).get("redis_pickle", False)
            serializer = "pickle" if use_pickle else "json"
            self.cache = RedisCache(self.config.redis_url, prefix=self.config.cache_prefix, serializer=serializer)
        else:
            self.cache = InMemoryCache()
        
        self._spatial_indexes = {}
        self.query_adapter = InMemoryQueryAdapter(self)

        if engine is not None:
            self.bind(engine)
        elif session is not None:
            self.bind(session)

    def bind(self, engine_or_session: Any, models: Optional[Dict[str, Any]] = None) -> None:
        """Bind a database engine or session to switch this facade to Database SQL mode."""
        self.query_adapter = DatabaseQueryAdapter(self, engine_or_session, models=models)

    def _get_shared_data(self, key: str, loader_fn: Any) -> Any:
        shm_cfg = self.config._config.get("shared_memory", {})
        shm_enabled = shm_cfg.get("enabled", False)
        
        cache_cfg = self.config._config.get("cache", {})
        redis_pickled = cache_cfg.get("redis_url") is not None and cache_cfg.get("redis_pickle", False)
        
        if shm_enabled:
            from py_nusantara.shared_memory import SharedMemoryCache
            shm_cache = SharedMemoryCache(prefix=shm_cfg.get("prefix", "nusantara_shm"))
            val = shm_cache.get(key)
            if val is not None:
                return val
            computed = loader_fn()
            shm_cache.set(key, computed)
            return computed
        elif redis_pickled:
            from py_nusantara.cache import RedisCache
            pickled_cache = RedisCache(self.config.redis_url, prefix=f"{self.config.cache_prefix}_pickled", serializer="pickle")
            return pickled_cache.remember(key, self.config.cache_ttl, loader_fn)
        else:
            return loader_fn()

    def provinces(self) -> List[ProvinceRecord]:
        """Fetch all provinces."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.provinces",
            ttl,
            lambda: self.query_adapter.provinces()
        )

    def find_province(self, id: str) -> Optional[ProvinceRecord]:
        """Fetch a specific province by ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.province.{id}",
            ttl,
            lambda: self.query_adapter.find_province(id)
        )

    def regencies_of(self, province_id: str) -> List[RegencyRecord]:
        """Fetch all regencies belonging to a province ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.regencies.{province_id}",
            ttl,
            lambda: self.query_adapter.regencies_of(province_id)
        )

    def find_regency(self, id: str) -> Optional[RegencyRecord]:
        """Fetch a specific regency by ID, falling back to historical mapping if obsolete."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.regency.{id}",
            ttl,
            lambda: self.query_adapter.find_regency(id)
        )

    def districts_of(self, regency_id: str) -> List[DistrictRecord]:
        """Fetch all districts belonging to a regency ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.districts.{regency_id}",
            ttl,
            lambda: self.query_adapter.districts_of(regency_id)
        )

    def find_district(self, id: str) -> Optional[DistrictRecord]:
        """Fetch a specific district by ID, falling back to historical mapping if obsolete."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.district.{id}",
            ttl,
            lambda: self.query_adapter.find_district(id)
        )

    def villages_of(self, district_id: str) -> List[VillageRecord]:
        """Fetch all villages belonging to a district ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.villages.{district_id}",
            ttl,
            lambda: self.query_adapter.villages_of(district_id)
        )

    def villages_of_province(self, province_id: str) -> List[VillageRecord]:
        """Fetch all villages belonging to a province ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.province_villages.{province_id}",
            ttl,
            lambda: self.query_adapter.villages_of_province(province_id)
        )

    def find_village(self, id: str) -> Optional[VillageRecord]:
        """Fetch a specific village by ID, falling back to historical mapping if obsolete."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.village.{id}",
            ttl,
            lambda: self.query_adapter.find_village(id)
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        offset: Optional[int] = None,
        cursor: Optional[str] = None,
        scope: Optional[Dict[str, str]] = None,
        fuzzy: bool = False,
        threshold: float = 0.6,
        similarity_method: str = "levenshtein",
    ) -> Dict[str, List[BaseRecord]]:
        """Search regional names dynamically across all levels, optionally scoped to a parent region."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        
        # Format scope into a string key for caching uniqueness
        scope_str = "none"
        if scope:
            scope_str = "_".join(f"{k}:{v}" for k, v in sorted(scope.items()))
        
        def _execute_search():
            return self.query_adapter.search(
                query,
                limit=limit,
                offset=offset,
                cursor=cursor,
                scope=scope,
                fuzzy=fuzzy,
                threshold=threshold,
                similarity_method=similarity_method,
            )

        cache_key = f"{prefix}.search.{query}.{limit}.{offset}.{cursor}.{scope_str}.{fuzzy}.{threshold}.{similarity_method}"
        return self.cache.remember(
            cache_key,
            ttl,
            _execute_search
        )



    def find_by_coordinate(
        self,
        latitude: float,
        longitude: float,
        fallback_to_nearest: bool = True,
    ) -> Dict[str, Optional[BaseRecord]]:
        """Resolve administrative regions (province, regency, district, village) containing the coordinate.
        
        If no exact boundary matches, can fallback to the nearest centroid.
        """
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.coord.{latitude}.{longitude}.{fallback_to_nearest}",
            ttl,
            lambda: self.query_adapter.find_by_coordinate(latitude, longitude, fallback_to_nearest)
        )

    def clear_cache(self) -> None:
        """Clear all cached queries."""
        self.cache.clear()
        self._spatial_indexes.clear()
        
        shm_enabled = self.config._config.get("shared_memory", {}).get("enabled", False)
        if shm_enabled:
            from py_nusantara.shared_memory import SharedMemoryCache
            shm_cache = SharedMemoryCache(prefix=self.config._config.get("shared_memory", {}).get("prefix", "nusantara_shm"))
            shm_cache.unlink_all()

    # --- Boundaries On-Demand Helpers ---
    def download_boundaries(
        self,
        levels: Union[str, List[str]] = "all",
        force: bool = False,
        cache_dir: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Any] = None,
    ) -> List[Path]:
        """Download geographic boundary shapefiles from CDN and verify their checksums."""
        return _download_boundaries(levels, force, cache_dir, self.config, progress_callback)

    def seed_boundaries(
        self,
        session: Any,
        levels: List[str] = ["provinces", "regencies", "districts", "villages"],
        force: bool = False,
        cache_dir: Optional[Union[str, Path]] = None,
        batch_size: int = 200,
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Seed boundaries into a database using SQLAlchemy connection."""
        seeder = NusantaraSeeder(session, self.config, self.reader)
        seeder.seed_boundaries(levels, force, cache_dir, batch_size, progress_callback)

    async def seed_boundaries_async(
        self,
        session: Any,
        levels: List[str] = ["provinces", "regencies", "districts", "villages"],
        force: bool = False,
        cache_dir: Optional[Union[str, Path]] = None,
        batch_size: int = 200,
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Seed boundaries into a database asynchronously using SQLAlchemy AsyncSession."""
        seeder = NusantaraSeeder(session, self.config, self.reader)
        await seeder.seed_boundaries_async(levels, force, cache_dir, batch_size, progress_callback)


    # --- Data Science DataFrame Helpers ---
    def provinces_df(self, logical: bool = True) -> Any:
        """Get all provinces as a pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([p.to_dict(logical) for p in self.provinces()])

    def regencies_df(self, province_id: str, logical: bool = True) -> Any:
        """Get regencies of a province as a pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([r.to_dict(logical) for r in self.regencies_of(province_id)])

    def districts_df(self, regency_id: str, logical: bool = True) -> Any:
        """Get districts of a regency as a pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([d.to_dict(logical) for d in self.districts_of(regency_id)])

    def villages_df(self, district_id: str, logical: bool = True) -> Any:
        """Get villages of a district as a pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([v.to_dict(logical) for v in self.villages_of(district_id)])

    def parse_nik(self, nik: str, reference_year: Optional[int] = None) -> NIKInfo:
        """Parse Nomor Induk Kependudukan (NIK) and resolve its location using this instance."""
        return _parse_nik(nik, reference_year=reference_year, facade_ref=self)

    def validate_nik(self, nik: str, reference_year: Optional[int] = None) -> bool:
        """Validate if the given NIK is syntactically valid."""
        return _validate_nik(nik, reference_year=reference_year)

    def parse_postal_code(self, postal_code: str) -> PostalCodeInfo:
        """Parse postal code and resolve its administrative region hierarchy using this instance (cached)."""
        cleaned_code = postal_code.strip()
        if not self.validate_postal_code(cleaned_code):
            raise PostalCodeValidationError(
                f"Invalid postal code format: '{postal_code}'. "
                "Must be exactly 5 numeric digits and cannot start with '0'."
            )
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.postal_code.{cleaned_code}",
            ttl,
            lambda: _parse_postal_code(cleaned_code, facade_ref=self)
        )

    def validate_postal_code(self, postal_code: str) -> bool:
        """Validate if the given postal code is a syntactically valid Indonesian postal code."""
        return _validate_postal_code(postal_code)

    def _get_spatial_index(self, level: str) -> Any:
        if level not in self._spatial_indexes:
            def _build_tree():
                records = []
                if level == "provinces":
                    records = self.provinces()
                elif level == "regencies":
                    records = [RegencyRecord(r, self.config, self) for r in self.reader.read_regencies()]
                elif level == "districts":
                    records = [DistrictRecord(r, self.config, self) for r in self.reader.read_districts()]
                elif level == "villages":
                    records = [VillageRecord(r, self.config, self) for r in self.reader.stream_all_villages()]
                from py_nusantara.spatial import KDTree
                return KDTree(records)
            self._spatial_indexes[level] = self._get_shared_data(f"kdtree_{level}", _build_tree)
        return self._spatial_indexes[level]

    def find_nearby(
        self, latitude: float, longitude: float, radius_km: float, level: str = "villages"
    ) -> List[BaseRecord]:
        """Find all regions of a specific level within the given radius (in kilometers) of a coordinate."""
        if level not in ("provinces", "regencies", "districts", "villages"):
            raise ValueError("level must be one of: provinces, regencies, districts, villages")

        spatial_index_enabled = self.config._config.get("boundaries", {}).get("spatial_index", True)
        if spatial_index_enabled:
            import math
            from py_nusantara.spatial import latlon_to_3d
            theta = radius_km / 6371.0
            r_3d = 2.0 * math.sin(theta / 2.0)
            query_pt_3d = latlon_to_3d(latitude, longitude)
            tree = self._get_spatial_index(level)
            candidates = tree.query_radius(query_pt_3d, r_3d)

            results = []
            for dist_3d, r in candidates:
                r_lat = getattr(r, "latitude", None)
                r_lon = getattr(r, "longitude", None)
                if r_lat is not None and r_lon is not None:
                    r.distance_km = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
                    results.append(r)
            results.sort(key=lambda x: getattr(x, "distance_km", 0.0))
            return results

        # Fallback to linear scan
        records: List[BaseRecord] = []
        if level == "provinces":
            records = self.provinces()
        elif level == "regencies":
            records = [RegencyRecord(r, self.config, self) for r in self.reader.read_regencies()]
        elif level == "districts":
            records = [DistrictRecord(r, self.config, self) for r in self.reader.read_districts()]
        elif level == "villages":
            # Optimization: prune by province centroid distance
            target_provinces = []
            for p in self.provinces():
                p_lat, p_lon = getattr(p, "latitude", None), getattr(p, "longitude", None)
                if p_lat is not None and p_lon is not None:
                    dist = haversine_distance(latitude, longitude, p_lat, p_lon)
                    if dist <= radius_km + 250.0:
                        target_provinces.append(p.id)
            
            if not target_provinces:
                target_provinces = [p.id for p in self.provinces()]
                
            for prov_id in target_provinces:
                records.extend(self.villages_of_province(prov_id))

        results = []
        for r in records:
            r_lat, r_lon = getattr(r, "latitude", None), getattr(r, "longitude", None)
            if r_lat is not None and r_lon is not None:
                dist = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
                if dist <= radius_km:
                    r.distance_km = dist
                    results.append(r)

        results.sort(key=lambda x: getattr(x, "distance_km", 0.0))
        return results

    def find_knn(
        self, latitude: float, longitude: float, k: int = 5, level: str = "villages"
    ) -> List[BaseRecord]:
        """Find the K nearest neighbors of a specific level to the given coordinate."""
        if level not in ("provinces", "regencies", "districts", "villages"):
            raise ValueError("level must be one of: provinces, regencies, districts, villages")

        spatial_index_enabled = self.config._config.get("boundaries", {}).get("spatial_index", True)
        if spatial_index_enabled:
            from py_nusantara.spatial import latlon_to_3d
            query_pt_3d = latlon_to_3d(latitude, longitude)
            tree = self._get_spatial_index(level)
            candidates = tree.query_knn(query_pt_3d, k)

            results = []
            for dist_3d, r in candidates:
                r_lat = getattr(r, "latitude", None)
                r_lon = getattr(r, "longitude", None)
                if r_lat is not None and r_lon is not None:
                    r.distance_km = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
                    results.append(r)
            return results

        # Fallback to linear scan
        records = []
        if level == "provinces":
            records = self.provinces()
        elif level == "regencies":
            records = [RegencyRecord(r, self.config, self) for r in self.reader.read_regencies()]
        elif level == "districts":
            records = [DistrictRecord(r, self.config, self) for r in self.reader.read_districts()]
        elif level == "villages":
            records = [VillageRecord(r, self.config, self) for r in self.reader.stream_all_villages()]

        results = []
        for r in records:
            r_lat = getattr(r, "latitude", None)
            r_lon = getattr(r, "longitude", None)
            if r_lat is not None and r_lon is not None:
                try:
                    dist = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
                    r.distance_km = dist
                    results.append(r)
                except (ValueError, TypeError):
                    pass

        results.sort(key=lambda x: getattr(x, "distance_km", 0.0))
        return results[:k]

    def find_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        level: str = "villages",
        use_boundary: bool = False,
    ) -> List[BaseRecord]:
        """Find all regions of a specific level that are within or intersect a bounding box."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.bbox.{min_lat}.{min_lon}.{max_lat}.{max_lon}.{level}.{use_boundary}",
            ttl,
            lambda: self.query_adapter.find_in_bbox(min_lat, min_lon, max_lat, max_lon, level, use_boundary)
        )

    def _execute_find_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        level: str = "villages",
        use_boundary: bool = False,
    ) -> List[BaseRecord]:
        if level not in ("provinces", "regencies", "districts", "villages"):
            raise ValueError("level must be one of: provinces, regencies, districts, villages")

        # Standardize coordinates
        min_lat, max_lat = min(min_lat, max_lat), max(min_lat, max_lat)
        min_lon, max_lon = min(min_lon, max_lon), max(min_lon, max_lon)

        records = []
        if level == "provinces":
            records = self.provinces()
        elif level == "regencies":
            records = [RegencyRecord(r, self.config, self) for r in self.reader.read_regencies()]
        elif level == "districts":
            records = [DistrictRecord(r, self.config, self) for r in self.reader.read_districts()]
        elif level == "villages":
            # Optimization: prune by province bounds
            target_provinces = []
            for p in self.provinces():
                p_lat, p_lon = getattr(p, "latitude", None), getattr(p, "longitude", None)
                if p_lat is not None and p_lon is not None:
                    # Expand province centroid by 3 degrees to cover its extent
                    p_min_lat = p_lat - 3.0
                    p_max_lat = p_lat + 3.0
                    p_min_lon = p_lon - 3.0
                    p_max_lon = p_lon + 3.0
                    if not (p_max_lat < min_lat or p_min_lat > max_lat or p_max_lon < min_lon or p_min_lon > max_lon):
                        target_provinces.append(p.id)

            if not target_provinces:
                return []

            for prov_id in target_provinces:
                records.extend(self.villages_of_province(prov_id))

        results = []
        for r in records:
            r_lat = getattr(r, "latitude", None)
            r_lon = getattr(r, "longitude", None)

            # Centroid check
            if r_lat is not None and r_lon is not None:
                try:
                    lat_f = float(r_lat)
                    lon_f = float(r_lon)
                    if min_lat <= lat_f <= max_lat and min_lon <= lon_f <= max_lon:
                        results.append(r)
                        continue
                except (ValueError, TypeError):
                    pass

            # Boundary check if requested
            if use_boundary:
                boundary_val = getattr(r, "boundary", None)
                if boundary_val:
                    if _is_boundary_in_bbox(boundary_val, min_lat, min_lon, max_lat, max_lon):
                        results.append(r)

        return results






# --- Default Shared Instance (Singleton-like facade shortcut) ---
_global_instance: Optional[Nusantara] = None
_instance_lock = threading.Lock()


def _get_instance() -> Nusantara:
    global _global_instance
    if _global_instance is None:
        with _instance_lock:
            if _global_instance is None:
                _global_instance = Nusantara()
    return _global_instance


def init(config_dict: Optional[Dict[str, Any]] = None) -> Nusantara:
    """Initialize or override the default global configuration instance."""
    global _global_instance
    _global_instance = Nusantara(config_dict)
    return _global_instance


def provinces() -> List[ProvinceRecord]:
    return _get_instance().provinces()


def find_province(id: str) -> Optional[ProvinceRecord]:
    return _get_instance().find_province(id)


def regencies_of(province_id: str) -> List[RegencyRecord]:
    return _get_instance().regencies_of(province_id)


def find_regency(id: str) -> Optional[RegencyRecord]:
    return _get_instance().find_regency(id)


def districts_of(regency_id: str) -> List[DistrictRecord]:
    return _get_instance().districts_of(regency_id)


def find_district(id: str) -> Optional[DistrictRecord]:
    return _get_instance().find_district(id)


def villages_of(district_id: str) -> List[VillageRecord]:
    return _get_instance().villages_of(district_id)


def find_village(id: str) -> Optional[VillageRecord]:
    return _get_instance().find_village(id)


def search(
    query: str,
    limit: int = 20,
    offset: Optional[int] = None,
    cursor: Optional[str] = None,
    scope: Optional[Dict[str, str]] = None,
    fuzzy: bool = False,
    threshold: float = 0.6,
    similarity_method: str = "levenshtein",
) -> Dict[str, List[BaseRecord]]:
    return _get_instance().search(
        query,
        limit,
        offset=offset,
        cursor=cursor,
        scope=scope,
        fuzzy=fuzzy,
        threshold=threshold,
        similarity_method=similarity_method,
    )




def find_by_coordinate(
    latitude: float,
    longitude: float,
    fallback_to_nearest: bool = True,
) -> Dict[str, Optional[BaseRecord]]:
    return _get_instance().find_by_coordinate(latitude, longitude, fallback_to_nearest)


def clear_cache() -> None:
    _get_instance().clear_cache()


# Boundaries Global Shortcuts
def download_boundaries(
    levels: Union[str, List[str]] = "all",
    force: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    progress_callback: Optional[Any] = None,
) -> List[Path]:
    return _get_instance().download_boundaries(levels, force, cache_dir, progress_callback)


def seed_boundaries(
    session: Any,
    levels: List[str] = ["provinces", "regencies", "districts", "villages"],
    force: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    batch_size: int = 200,
    progress_callback: Optional[Any] = None,
) -> None:
    _get_instance().seed_boundaries(session, levels, force, cache_dir, batch_size, progress_callback)


async def seed_boundaries_async(
    session: Any,
    levels: List[str] = ["provinces", "regencies", "districts", "villages"],
    force: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    batch_size: int = 200,
    progress_callback: Optional[Any] = None,
) -> None:
    await _get_instance().seed_boundaries_async(session, levels, force, cache_dir, batch_size, progress_callback)



# DataFrame Shortcuts
def provinces_df(logical: bool = True) -> Any:
    return _get_instance().provinces_df(logical)


def regencies_df(province_id: str, logical: bool = True) -> Any:
    return _get_instance().regencies_df(province_id, logical)


def districts_df(regency_id: str, logical: bool = True) -> Any:
    return _get_instance().districts_df(regency_id, logical)


def villages_df(district_id: str, logical: bool = True) -> Any:
    return _get_instance().villages_df(district_id, logical)


# NIK Shortcuts
def parse_nik(nik: str, reference_year: Optional[int] = None) -> NIKInfo:
    return _get_instance().parse_nik(nik, reference_year=reference_year)


def validate_nik(nik: str, reference_year: Optional[int] = None) -> bool:
    return _get_instance().validate_nik(nik, reference_year=reference_year)


# Postal Code Shortcuts
def parse_postal_code(postal_code: str) -> PostalCodeInfo:
    return _get_instance().parse_postal_code(postal_code)


def validate_postal_code(postal_code: str) -> bool:
    return _get_instance().validate_postal_code(postal_code)


# Spatial shortcuts
def find_nearby(
    latitude: float, longitude: float, radius_km: float, level: str = "villages"
) -> List[BaseRecord]:
    return _get_instance().find_nearby(latitude, longitude, radius_km, level=level)


def find_knn(
    latitude: float, longitude: float, k: int = 5, level: str = "villages"
) -> List[BaseRecord]:
    return _get_instance().find_knn(latitude, longitude, k=k, level=level)


def find_in_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    level: str = "villages",
    use_boundary: bool = False,
) -> List[BaseRecord]:
    return _get_instance().find_in_bbox(
        min_lat, min_lon, max_lat, max_lon, level=level, use_boundary=use_boundary
    )



# Historical mapping shortcut
def resolve_legacy_id(region_id: str) -> str:
    """Map legacy/obsolete regional ID to the current active ID."""
    from py_nusantara.historical import resolve_legacy_id as _resolve
    return _resolve(region_id)




