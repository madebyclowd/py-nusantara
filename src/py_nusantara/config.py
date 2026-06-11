import os
from typing import Dict, Any, Optional
from py_nusantara.exceptions import ConfigurationError


class NusantaraConfig:
    """Configuration manager for py-nusantara."""

    DEFAULT_CONFIG: Dict[str, Any] = {
        "tables": {
            "provinces": "provinces",
            "regencies": "regencies",
            "districts": "districts",
            "villages": "villages",
        },
        "enable_foreign_keys": True,
        "columns": {
            "provinces": {
                "id": {"name": "id", "enabled": True},
                "name": {"name": "name", "enabled": True},
                "capital": {"name": "capital", "enabled": True},
                "latitude": {"name": "latitude", "enabled": True},
                "longitude": {"name": "longitude", "enabled": True},
                "elevation": {"name": "elevation", "enabled": True},
                "timezone": {"name": "timezone", "enabled": True},
                "area": {"name": "area", "enabled": True},
                "population": {"name": "population", "enabled": True},
                "boundary": {"name": "boundary", "enabled": False},
            },
            "regencies": {
                "id": {"name": "id", "enabled": True},
                "province_id": {"name": "province_id", "enabled": True},
                "name": {"name": "name", "enabled": True},
                "capital": {"name": "capital", "enabled": True},
                "latitude": {"name": "latitude", "enabled": True},
                "longitude": {"name": "longitude", "enabled": True},
                "elevation": {"name": "elevation", "enabled": True},
                "timezone": {"name": "timezone", "enabled": True},
                "area": {"name": "area", "enabled": True},
                "population": {"name": "population", "enabled": True},
                "boundary": {"name": "boundary", "enabled": False},
            },
            "districts": {
                "id": {"name": "id", "enabled": True},
                "regency_id": {"name": "regency_id", "enabled": True},
                "name": {"name": "name", "enabled": True},
                "latitude": {"name": "latitude", "enabled": True},
                "longitude": {"name": "longitude", "enabled": True},
                "boundary": {"name": "boundary", "enabled": False},
            },
            "villages": {
                "id": {"name": "id", "enabled": True},
                "district_id": {"name": "district_id", "enabled": True},
                "name": {"name": "name", "enabled": True},
                "postal_code": {"name": "postal_code", "enabled": True},
                "latitude": {"name": "latitude", "enabled": True},
                "longitude": {"name": "longitude", "enabled": True},
                "boundary": {"name": "boundary", "enabled": False},
            },
        },
        "cache": {
            "enabled": True,
            "ttl": 86400,
            "prefix": "nusantara",
            "redis_url": None, # e.g. "redis://localhost:6379/0"
        },
        "boundaries": {
            "cdn_url": "https://github.com/madebyclowd/laravel-nusantara/releases/download",
            "local_path": None,
            "version": "v1.1.0",
            "type": "spatial",  # "spatial" or "text"
            "spatial_index": True,
            "verify_checksum": True,
            "levels": {
                "provinces": True,
                "regencies": True,
                "districts": False,
                "villages": False,
            },
        },
    }

    REQUIRED_KEYS = {
        "provinces": {"id"},
        "regencies": {"id", "province_id"},
        "districts": {"id", "regency_id"},
        "villages": {"id", "district_id"},
    }

    def __init__(self, custom_config: Optional[Dict[str, Any]] = None):
        self._config = self._deep_merge(self.DEFAULT_CONFIG, custom_config or {})
        self.validate()

    def _deep_merge(self, base: Dict[str, Any], custom: Dict[str, Any]) -> Dict[str, Any]:
        merged = base.copy()
        for k, v in custom.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = self._deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    def validate(self) -> None:
        """Validate that all required keys are enabled."""
        for level, keys in self.REQUIRED_KEYS.items():
            level_cols = self._config.get("columns", {}).get(level, {})
            for key in keys:
                col_cfg = level_cols.get(key)
                if not col_cfg or not col_cfg.get("enabled", False):
                    raise ConfigurationError(
                        f"Referential integrity violation: column '{key}' in '{level}' "
                        "is a primary/foreign key and MUST be enabled in configuration."
                    )

    def get_table_name(self, level: str) -> str:
        """Get the database table name for a level (provinces, regencies, etc.)."""
        return self._config.get("tables", {}).get(level, level)

    def get_columns(self, level: str) -> Dict[str, Dict[str, Any]]:
        """Get columns configuration dictionary for a level."""
        return self._config.get("columns", {}).get(level, {})

    def resolve_column_name(self, level: str, logical_name: str) -> str:
        """Resolve a logical attribute/column name to the actual database/CSV name."""
        col_cfg = self.get_columns(level).get(logical_name)
        if col_cfg and col_cfg.get("enabled", False):
            return col_cfg.get("name", logical_name)
        return logical_name

    def is_column_enabled(self, level: str, logical_name: str) -> bool:
        """Check if a logical column is enabled."""
        col_cfg = self.get_columns(level).get(logical_name)
        return bool(col_cfg and col_cfg.get("enabled", False))

    @property
    def cache_enabled(self) -> bool:
        return bool(self._config.get("cache", {}).get("enabled", True))

    @property
    def cache_ttl(self) -> int:
        return int(self._config.get("cache", {}).get("ttl", 86400))

    @property
    def cache_prefix(self) -> str:
        return str(self._config.get("cache", {}).get("prefix", "nusantara"))

    @property
    def redis_url(self) -> Optional[str]:
        return self._config.get("cache", {}).get("redis_url")
