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
from py_nusantara.spatial import is_point_in_boundary, haversine_distance
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
    "resolve_legacy_id",
]


class Nusantara:
    """The central access point (Facade) for py-nusantara administrative regions."""

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None) -> None:
        self.config = NusantaraConfig(config_dict)
        self.reader = NusantaraReader(self.config)
        self.searcher = NusantaraSearch(self.config, self.reader)
        
        # Pluggable caching configuration
        if not self.config.cache_enabled:
            self.cache = NoCache()
        elif self.config.redis_url:
            self.cache = RedisCache(self.config.redis_url, prefix=self.config.cache_prefix)
        else:
            self.cache = InMemoryCache()
        
        self._spatial_indexes = {}

    def provinces(self) -> List[ProvinceRecord]:
        """Fetch all provinces."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.provinces",
            ttl,
            lambda: [ProvinceRecord(r, self.config, self) for r in self.reader.read_provinces()]
        )

    def find_province(self, id: str) -> Optional[ProvinceRecord]:
        """Fetch a specific province by ID."""
        id_col = self.config.resolve_column_name("provinces", "id")
        for p in self.provinces():
            if getattr(p, id_col) == id:
                return p
        return None

    def regencies_of(self, province_id: str) -> List[RegencyRecord]:
        """Fetch all regencies belonging to a province ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        prov_id_col = self.config.resolve_column_name("regencies", "province_id")
        return self.cache.remember(
            f"{prefix}.regencies.{province_id}",
            ttl,
            lambda: [
                RegencyRecord(r, self.config, self)
                for r in self.reader.read_regencies()
                if r.get(prov_id_col) == province_id
            ]
        )

    def find_regency(self, id: str) -> Optional[RegencyRecord]:
        """Fetch a specific regency by ID, falling back to historical mapping if obsolete."""
        prov_id = id[:2]
        id_col = self.config.resolve_column_name("regencies", "id")
        for r in self.regencies_of(prov_id):
            if getattr(r, id_col) == id:
                return r
        # Fallback to historical mapping
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_regency(active_id)
        return None

    def districts_of(self, regency_id: str) -> List[DistrictRecord]:
        """Fetch all districts belonging to a regency ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        reg_id_col = self.config.resolve_column_name("districts", "regency_id")
        return self.cache.remember(
            f"{prefix}.districts.{regency_id}",
            ttl,
            lambda: [
                DistrictRecord(r, self.config, self)
                for r in self.reader.read_districts()
                if r.get(reg_id_col) == regency_id
            ]
        )

    def find_district(self, id: str) -> Optional[DistrictRecord]:
        """Fetch a specific district by ID, falling back to historical mapping if obsolete."""
        reg_id = id[:4]
        id_col = self.config.resolve_column_name("districts", "id")
        for d in self.districts_of(reg_id):
            if getattr(d, id_col) == id:
                return d
        # Fallback to historical mapping
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_district(active_id)
        return None

    def villages_of(self, district_id: str) -> List[VillageRecord]:
        """Fetch all villages belonging to a district ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.villages.{district_id}",
            ttl,
            lambda: [
                VillageRecord(r, self.config, self)
                for r in self.reader.read_villages(district_id=district_id)
            ]
        )

    def villages_of_province(self, province_id: str) -> List[VillageRecord]:
        """Fetch all villages belonging to a province ID."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        return self.cache.remember(
            f"{prefix}.province_villages.{province_id}",
            ttl,
            lambda: [
                VillageRecord(r, self.config, self)
                for r in self.reader.read_villages(province_id=province_id)
            ]
        )

    def find_village(self, id: str) -> Optional[VillageRecord]:
        """Fetch a specific village by ID, falling back to historical mapping if obsolete."""
        dist_id = id[:6]
        id_col = self.config.resolve_column_name("villages", "id")
        for v in self.villages_of(dist_id):
            if getattr(v, id_col) == id:
                return v
        # Fallback to historical mapping
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_village(active_id)
        return None

    def search(
        self, query: str, limit: int = 20, scope: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[BaseRecord]]:
        """Search regional names dynamically across all levels, optionally scoped to a parent region."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        
        # Format scope into a string key for caching uniqueness
        scope_str = "none"
        if scope:
            scope_str = "_".join(f"{k}:{v}" for k, v in sorted(scope.items()))
        
        def _execute_search():
            raw_res = self.searcher.search(query, limit, scope)
            return {
                "provinces": [ProvinceRecord(r, self.config, self) for r in raw_res["provinces"]],
                "regencies": [RegencyRecord(r, self.config, self) for r in raw_res["regencies"]],
                "districts": [DistrictRecord(r, self.config, self) for r in raw_res["districts"]],
                "villages": [VillageRecord(r, self.config, self) for r in raw_res["villages"]],
            }

        return self.cache.remember(
            f"{prefix}.search.{query}.{limit}.{scope_str}",
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
        
        def _execute_resolve():
            res: Dict[str, Optional[BaseRecord]] = {
                "province": None,
                "regency": None,
                "district": None,
                "village": None,
            }
            
            def _find_nearest(records: List[Any]) -> Optional[Any]:
                nearest = None
                min_dist = float("inf")
                for r in records:
                    r_lat = getattr(r, "latitude", None)
                    r_lon = getattr(r, "longitude", None)
                    if r_lat is not None and r_lon is not None:
                        try:
                            dist = haversine_distance(latitude, longitude, float(r_lat), float(r_lon))
                            if dist < min_dist:
                                min_dist = dist
                                nearest = r
                        except (ValueError, TypeError):
                            pass
                return nearest

            # 1. Resolve Province
            prov_records = self.provinces()
            matched_prov = None
            
            for p in prov_records:
                boundary_val = getattr(p, "boundary", None)
                if boundary_val and is_point_in_boundary(latitude, longitude, boundary_val):
                    matched_prov = p
                    break
                    
            if not matched_prov and fallback_to_nearest:
                matched_prov = _find_nearest(prov_records)
                
            if not matched_prov:
                return res
            res["province"] = matched_prov

            # 2. Resolve Regency
            reg_records = self.regencies_of(matched_prov.id)
            matched_reg = None
            for r in reg_records:
                boundary_val = getattr(r, "boundary", None)
                if boundary_val and is_point_in_boundary(latitude, longitude, boundary_val):
                    matched_reg = r
                    break
                    
            if not matched_reg and fallback_to_nearest:
                matched_reg = _find_nearest(reg_records)
                
            if not matched_reg:
                return res
            res["regency"] = matched_reg

            # 3. Resolve District
            dist_records = self.districts_of(matched_reg.id)
            matched_dist = None
            for d in dist_records:
                boundary_val = getattr(d, "boundary", None)
                if boundary_val and is_point_in_boundary(latitude, longitude, boundary_val):
                    matched_dist = d
                    break
                    
            if not matched_dist and fallback_to_nearest:
                matched_dist = _find_nearest(dist_records)
                
            if not matched_dist:
                return res
            res["district"] = matched_dist

            # 4. Resolve Village
            vil_records = self.villages_of(matched_dist.id)
            matched_vil = None
            for v in vil_records:
                boundary_val = getattr(v, "boundary", None)
                if boundary_val and is_point_in_boundary(latitude, longitude, boundary_val):
                    matched_vil = v
                    break
                    
            if not matched_vil and fallback_to_nearest:
                matched_vil = _find_nearest(vil_records)
                
            res["village"] = matched_vil
            return res

        return self.cache.remember(
            f"{prefix}.coord.{latitude}.{longitude}.{fallback_to_nearest}",
            ttl,
            _execute_resolve
        )

    def clear_cache(self) -> None:
        """Clear all cached queries."""
        self.cache.clear()
        self._spatial_indexes.clear()

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
            self._spatial_indexes[level] = KDTree(records)
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
    query: str, limit: int = 20, scope: Optional[Dict[str, str]] = None
) -> Dict[str, List[BaseRecord]]:
    return _get_instance().search(query, limit, scope=scope)



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


# Historical mapping shortcut
def resolve_legacy_id(region_id: str) -> str:
    """Map legacy/obsolete regional ID to the current active ID."""
    from py_nusantara.historical import resolve_legacy_id as _resolve
    return _resolve(region_id)




