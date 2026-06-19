from typing import Any, Dict, List, Optional


class BaseRecord:
    """Base class for regional record wrappers."""
    _level: str = ""

    def __init__(self, data: Dict[str, Any], config: Any, facade_ref: Optional[Any] = None):
        self._data = data
        self._config = config
        self._facade = facade_ref

    def __getattr__(self, name: str) -> Any:
        # Check if the logical name matches
        db_name = self._config.resolve_column_name(self._level, name)
        if db_name in self._data:
            val = self._data[db_name]
            # Convert float coordinates to float if needed
            if name in ("latitude", "longitude", "area", "elevation") and val is not None:
                try:
                    return float(val)
                except ValueError:
                    return val
            if name == "population" and val is not None:
                try:
                    return int(val)
                except ValueError:
                    return val
            return val

        # If it's a known but disabled column, raise attribute error indicating it's disabled
        col_cfg = self._config.get_columns(self._level).get(name)
        if col_cfg and not col_cfg.get("enabled", False):
            raise AttributeError(
                f"Attribute '{name}' is disabled in configuration for {self.__class__.__name__}."
            )

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        try:
            return self.__getattr__(key)
        except AttributeError as e:
            raise KeyError(str(e))

    def to_dict(self, logical: bool = True) -> Dict[str, Any]:
        """Convert the record to a dictionary.
        
        If logical is True, keys will be logical names (e.g. 'name').
        If logical is False, keys will be actual database/CSV column names.
        """
        if not logical:
            return self._data.copy()

        res = {}
        for logical_name, col_cfg in self._config.get_columns(self._level).items():
            if col_cfg.get("enabled", False):
                db_name = col_cfg.get("name", logical_name)
                if db_name in self._data:
                    res[logical_name] = getattr(self, logical_name)
        return res

    def __repr__(self) -> str:
        try:
            name_val = getattr(self, "name")
            id_val = getattr(self, "id")
            return f"<{self.__class__.__name__} id={id_val} name='{name_val}'>"
        except AttributeError:
            return f"<{self.__class__.__name__} data={self._data}>"


class ProvinceRecord(BaseRecord):
    """Wrapper for a Province record."""
    _level = "provinces"

    @property
    def regencies(self) -> List["RegencyRecord"]:
        """Get all regencies belonging to this province."""
        if not self._facade:
            return []
        return self._facade.regencies_of(self.id)

    @property
    def districts(self) -> List["DistrictRecord"]:
        """Get all districts belonging to this province through regencies."""
        if not self._facade:
            return []
        districts = []
        for regency in self.regencies:
            districts.extend(regency.districts)
        return districts

    @property
    def villages(self) -> List["VillageRecord"]:
        """Get all villages belonging to this province."""
        if not self._facade:
            return []
        # Leverage partition: fetch villages directly by province ID
        return self._facade.villages_of_province(self.id)


class RegencyRecord(BaseRecord):
    """Wrapper for a Regency record."""
    _level = "regencies"

    @property
    def province(self) -> Optional[ProvinceRecord]:
        """Get the province that owns this regency."""
        if not self._facade:
            return None
        return self._facade.find_province(self.province_id)

    @property
    def districts(self) -> List["DistrictRecord"]:
        """Get all districts belonging to this regency."""
        if not self._facade:
            return []
        return self._facade.districts_of(self.id)

    @property
    def villages(self) -> List["VillageRecord"]:
        """Get all villages belonging to this regency through districts."""
        if not self._facade:
            return []
        villages = []
        for district in self.districts:
            villages.extend(district.villages)
        return villages

    @property
    def is_city(self) -> bool:
        """Return True if this regency is officially a City (Kota)."""
        name_val = getattr(self, "name", "")
        return name_val.upper().startswith("KOTA")

    @property
    def type(self) -> str:
        """Return 'Kota' if this is a City, else 'Kabupaten'."""
        return "Kota" if self.is_city else "Kabupaten"


class DistrictRecord(BaseRecord):
    """Wrapper for a District record."""
    _level = "districts"

    @property
    def regency(self) -> Optional[RegencyRecord]:
        """Get the regency that owns this district."""
        if not self._facade:
            return None
        return self._facade.find_regency(self.regency_id)

    @property
    def province(self) -> Optional[ProvinceRecord]:
        """Get the province that owns this district."""
        if not self._facade:
            return None
        return self._facade.find_province(self.id[:2])

    @property
    def villages(self) -> List["VillageRecord"]:
        """Get all villages belonging to this district."""
        if not self._facade:
            return []
        return self._facade.villages_of(self.id)


class VillageRecord(BaseRecord):
    """Wrapper for a Village record."""
    _level = "villages"

    @property
    def district(self) -> Optional[DistrictRecord]:
        """Get the district that owns this village."""
        if not self._facade:
            return None
        return self._facade.find_district(self.district_id)

    @property
    def regency(self) -> Optional[RegencyRecord]:
        """Get the regency that owns this village."""
        if not self._facade:
            return None
        return self._facade.find_regency(self.id[:4])

    @property
    def province(self) -> Optional[ProvinceRecord]:
        """Get the province that owns this village."""
        if not self._facade:
            return None
        return self._facade.find_province(self.id[:2])

