import csv
import gzip
import sys
import logging
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional
from py_nusantara.config import NusantaraConfig
from py_nusantara.exceptions import DataNotFoundError
from py_nusantara.manifest import Manifest

logger = logging.getLogger("py_nusantara")

# Increase CSV field size limit to support large geographic boundary coordinate shapes.
max_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_limit)
        break
    except OverflowError:
        max_limit = int(max_limit / 10)


class NusantaraReader:
    """Reads and streams gzipped CSV data with integrity validation and configuration filtering."""

    def __init__(self, config: NusantaraConfig, data_dir: Optional[Path] = None):
        self.config = config
        # Default data directory is src/py_nusantara/data
        self.data_dir = data_dir or (Path(__file__).parent / "data")

    def _get_file_path(self, relative_path: str) -> Path:
        """Resolve path, preferring the boundary cache directory if it exists and matches checksum.
        
        Falls back to shipped core files if not found in cache.
        """
        boundaries_cfg = self.config._config.get("boundaries", {})
        local_path = boundaries_cfg.get("local_path")
        if local_path:
            cache_dir = Path(local_path)
        else:
            cache_dir = Path.home() / ".cache" / "py-nusantara"

        # The filename in HASHES is the basename
        filename = Path(relative_path).name

        # 1. Try to read from local boundary cache folder
        cache_filepath = cache_dir / filename
        if cache_filepath.exists():
            verify_checksum = boundaries_cfg.get("verify_checksum", True)
            if verify_checksum:
                try:
                    Manifest.verify(cache_filepath)
                    return cache_filepath
                except Exception as e:
                    logger.warning(f"Cached file integrity check failed for {filename}: {e}. Falling back to core package files.")
            else:
                return cache_filepath

        # 2. Fallback to package core files (shipped defaults without boundaries)
        # Securely resolve path to prevent directory traversal
        resolved_data_dir = self.data_dir.resolve()
        filepath = (resolved_data_dir / relative_path).resolve()
        if not filepath.is_relative_to(resolved_data_dir):
            logger.error(f"Directory traversal attempt blocked: {relative_path}")
            raise ValueError("Directory traversal attempt detected.")

        if not filepath.exists():
            raise DataNotFoundError(f"Dataset file not found: {filepath}")

        # Core packaged files do not contain boundaries and will not match release hashes,
        # so we do not run Manifest.verify() on them.
        return filepath

    def _stream_csv(self, filepath: Path, level: str) -> Generator[Dict[str, Any], None, None]:
        """Read gzipped CSV file and yield dictionary rows matching column configurations."""
        columns_cfg = self.config.get_columns(level)

        with gzip.open(filepath, "rt", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                return

            for row in reader:
                if len(headers) != len(row):
                    continue  # Malformed row, skip
                
                raw_record = dict(zip(headers, row))
                db_record = {}

                # Map raw record attributes to configured names and check if enabled
                for logical_name, col_cfg in columns_cfg.items():
                    if col_cfg.get("enabled", False) and logical_name in raw_record:
                        db_name = col_cfg.get("name", logical_name)
                        val = raw_record[logical_name]
                        db_record[db_name] = None if val == "" else val

                yield db_record

    def read_provinces(self) -> List[Dict[str, Any]]:
        """Read all provinces from dataset."""
        path = self._get_file_path("provinces.csv.gz")
        return list(self._stream_csv(path, "provinces"))

    def read_regencies(self) -> List[Dict[str, Any]]:
        """Read all regencies from dataset."""
        path = self._get_file_path("regencies.csv.gz")
        return list(self._stream_csv(path, "regencies"))

    def read_districts(self) -> List[Dict[str, Any]]:
        """Read all districts from dataset."""
        path = self._get_file_path("districts.csv.gz")
        return list(self._stream_csv(path, "districts"))

    def stream_all_villages(self) -> Iterator[Dict[str, Any]]:
        """Stream villages from all partitioned village files sequentially, preferring cache."""
        village_files = sorted([k for k in Manifest.HASHES.keys() if k.startswith("villages_")])
        for filename in village_files:
            try:
                # _get_file_path checks cache first, then falls back to core/villages/...
                filepath = self._get_file_path(f"villages/{filename}")
                yield from self._stream_csv(filepath, "villages")
            except DataNotFoundError:
                continue

    def read_villages(
        self, 
        province_id: Optional[str] = None, 
        district_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Read villages, optimized by partitioning.
        
        If province_id is provided, only loads villages for that province.
        If district_id is provided, resolves province from district prefix and filters.
        If neither is provided, reads all villages.
        """
        # Resolve target province file if possible
        target_prov = None
        if province_id:
            target_prov = province_id
        elif district_id:
            # District ID pattern: e.g. "110101" -> first 2 characters are Province ID ("11")
            target_prov = district_id[:2]

        if target_prov:
            filename = f"villages/villages_{target_prov}.csv.gz"
            try:
                filepath = self._get_file_path(filename)
            except DataNotFoundError:
                # If a province file doesn't exist, return empty list (e.g. invalid ID)
                return []
            
            records = self._stream_csv(filepath, "villages")
            if district_id:
                # Filter by district column. Note: we need to filter by resolved column name
                district_col = self.config.resolve_column_name("villages", "district_id")
                return [r for r in records if r.get(district_col) == district_id]
            return list(records)

        # Fallback to loading all villages
        return list(self.stream_all_villages())
