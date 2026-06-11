from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from py_nusantara.config import NusantaraConfig
from py_nusantara.exceptions import (
    NusantaraError,
    ConfigurationError,
    IntegrityError,
    DataNotFoundError,
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

__all__ = [
    "Nusantara",
    "NusantaraError",
    "ConfigurationError",
    "IntegrityError",
    "DataNotFoundError",
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
    "provinces_df",
    "regencies_df",
    "districts_df",
    "villages_df",
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
            self.cache = RedisCache(self.config.redis_url)
        else:
            self.cache = InMemoryCache()

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
        """Fetch a specific regency by ID."""
        prov_id = id[:2]
        id_col = self.config.resolve_column_name("regencies", "id")
        for r in self.regencies_of(prov_id):
            if getattr(r, id_col) == id:
                return r
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
        """Fetch a specific district by ID."""
        reg_id = id[:4]
        id_col = self.config.resolve_column_name("districts", "id")
        for d in self.districts_of(reg_id):
            if getattr(d, id_col) == id:
                return d
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
        """Fetch a specific village by ID."""
        dist_id = id[:6]
        id_col = self.config.resolve_column_name("villages", "id")
        for v in self.villages_of(dist_id):
            if getattr(v, id_col) == id:
                return v
        return None

    def search(self, query: str, limit: int = 20) -> Dict[str, List[BaseRecord]]:
        """Search regional names dynamically across all levels."""
        prefix = self.config.cache_prefix
        ttl = self.config.cache_ttl
        
        def _execute_search():
            raw_res = self.searcher.search(query, limit)
            return {
                "provinces": [ProvinceRecord(r, self.config, self) for r in raw_res["provinces"]],
                "regencies": [RegencyRecord(r, self.config, self) for r in raw_res["regencies"]],
                "districts": [DistrictRecord(r, self.config, self) for r in raw_res["districts"]],
                "villages": [VillageRecord(r, self.config, self) for r in raw_res["villages"]],
            }

        return self.cache.remember(
            f"{prefix}.search.{query}.{limit}",
            ttl,
            _execute_search
        )

    def clear_cache(self) -> None:
        """Clear all cached queries."""
        self.cache.clear()

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


# --- Default Shared Instance (Singleton-like facade shortcut) ---
_global_instance: Optional[Nusantara] = None


def _get_instance() -> Nusantara:
    global _global_instance
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


def search(query: str, limit: int = 20) -> Dict[str, List[BaseRecord]]:
    return _get_instance().search(query, limit)


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
