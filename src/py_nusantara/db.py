from typing import Any, Dict, List, Optional, Type, Union
import gzip
import csv
import logging
from pathlib import Path
from py_nusantara.config import NusantaraConfig
from py_nusantara.reader import NusantaraReader
from py_nusantara.downloader import json_to_wkt, get_default_cache_dir
from py_nusantara.exceptions import DataNotFoundError

logger = logging.getLogger("py_nusantara")

try:
    import sqlalchemy as sa
    from sqlalchemy.orm import relationship
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


def build_models(base_class: Any, config: NusantaraConfig) -> Dict[str, Type]:
    """Dynamically construct SQLAlchemy models (Province, Regency, District, Village) based on config.
    
    Args:
        base_class: The SQLAlchemy declarative base class.
        config: The NusantaraConfig instance.
        
    Returns:
        A dictionary containing the generated model classes: {"Province": Province, ...}
    """
    if not SQLALCHEMY_AVAILABLE:
        raise ImportError(
            "SQLAlchemy is required to use build_models. "
            "Install it via: pip install py-nusantara[sqlalchemy] or uv add sqlalchemy"
        )

    # 1. Gather configured table and column names
    prov_table = config.get_table_name("provinces")
    reg_table = config.get_table_name("regencies")
    dist_table = config.get_table_name("districts")
    vil_table = config.get_table_name("villages")

    # Helper to resolve DB column name
    def db_col(level: str, name: str) -> str:
        return config.resolve_column_name(level, name)

    # Resolve boundary column type
    boundary_type = sa.Text
    if config.use_geoalchemy2:
        try:
            import geoalchemy2 as ga
            boundary_type = ga.Geometry(geometry_type='GEOMETRY', srid=4326)
        except ImportError:
            raise ImportError(
                "geoalchemy2 is required when use_geoalchemy2 is enabled. "
                "Install it via: pip install geoalchemy2 or uv add geoalchemy2"
            )

    def _orm_to_geojson(self) -> Dict[str, Any]:
        props = {}
        boundary_val = None
        for attr_name in self.__mapper__.column_attrs.keys():
            val = getattr(self, attr_name, None)
            if attr_name == "boundary":
                boundary_val = val
            else:
                props[attr_name] = val

        from py_nusantara.spatial import parse_boundary_to_geojson_geometry
        geom = None
        if boundary_val:
            geom = parse_boundary_to_geojson_geometry(boundary_val)

        if not geom:
            lat = getattr(self, "latitude", None)
            lon = getattr(self, "longitude", None)
            if lat is not None and lon is not None:
                try:
                    geom = {
                        "type": "Point",
                        "coordinates": [float(lon), float(lat)]
                    }
                except (ValueError, TypeError):
                    pass

        return {
            "type": "Feature",
            "geometry": geom,
            "properties": props
        }

    # 2. Build Province Attributes
    prov_attrs = {
        "__tablename__": prov_table,
        "__mapper_args__": {"confirm_deleted_rows": False},
        "to_geojson": _orm_to_geojson,
    }
    
    # Map fields dynamically if enabled in config
    if config.is_column_enabled("provinces", "id"):
        prov_attrs["id"] = sa.Column(db_col("provinces", "id"), sa.String(2), primary_key=True)
    if config.is_column_enabled("provinces", "name"):
        prov_attrs["name"] = sa.Column(db_col("provinces", "name"), sa.String(100), nullable=False)
    if config.is_column_enabled("provinces", "capital"):
        prov_attrs["capital"] = sa.Column(db_col("provinces", "capital"), sa.String(100))
    if config.is_column_enabled("provinces", "latitude"):
        prov_attrs["latitude"] = sa.Column(db_col("provinces", "latitude"), sa.Float)
    if config.is_column_enabled("provinces", "longitude"):
        prov_attrs["longitude"] = sa.Column(db_col("provinces", "longitude"), sa.Float)
    if config.is_column_enabled("provinces", "elevation"):
        prov_attrs["elevation"] = sa.Column(db_col("provinces", "elevation"), sa.Float)
    if config.is_column_enabled("provinces", "timezone"):
        prov_attrs["timezone"] = sa.Column(db_col("provinces", "timezone"), sa.String(20))
    if config.is_column_enabled("provinces", "area"):
        prov_attrs["area"] = sa.Column(db_col("provinces", "area"), sa.Float)
    if config.is_column_enabled("provinces", "population"):
        prov_attrs["population"] = sa.Column(db_col("provinces", "population"), sa.Integer)
    if config.is_column_enabled("provinces", "boundary"):
        prov_attrs["boundary"] = sa.Column(db_col("provinces", "boundary"), boundary_type)

    # 3. Build Regency Attributes
    reg_attrs = {
        "__tablename__": reg_table,
        "__mapper_args__": {"confirm_deleted_rows": False},
        "to_geojson": _orm_to_geojson,
    }
    if config.is_column_enabled("regencies", "id"):
        reg_attrs["id"] = sa.Column(db_col("regencies", "id"), sa.String(4), primary_key=True)
    if config.is_column_enabled("regencies", "province_id"):
        reg_attrs["province_id"] = sa.Column(
            db_col("regencies", "province_id"), 
            sa.String(2), 
            sa.ForeignKey(f"{prov_table}.{db_col('provinces', 'id')}")
        )
    if config.is_column_enabled("regencies", "name"):
        reg_attrs["name"] = sa.Column(db_col("regencies", "name"), sa.String(100), nullable=False)
    if config.is_column_enabled("regencies", "capital"):
        reg_attrs["capital"] = sa.Column(db_col("regencies", "capital"), sa.String(100))
    if config.is_column_enabled("regencies", "latitude"):
        reg_attrs["latitude"] = sa.Column(db_col("regencies", "latitude"), sa.Float)
    if config.is_column_enabled("regencies", "longitude"):
        reg_attrs["longitude"] = sa.Column(db_col("regencies", "longitude"), sa.Float)
    if config.is_column_enabled("regencies", "elevation"):
        reg_attrs["elevation"] = sa.Column(db_col("regencies", "elevation"), sa.Float)
    if config.is_column_enabled("regencies", "timezone"):
        reg_attrs["timezone"] = sa.Column(db_col("regencies", "timezone"), sa.String(20))
    if config.is_column_enabled("regencies", "area"):
        reg_attrs["area"] = sa.Column(db_col("regencies", "area"), sa.Float)
    if config.is_column_enabled("regencies", "population"):
        reg_attrs["population"] = sa.Column(db_col("regencies", "population"), sa.Integer)
    if config.is_column_enabled("regencies", "boundary"):
        reg_attrs["boundary"] = sa.Column(db_col("regencies", "boundary"), boundary_type)

    # 4. Build District Attributes
    dist_attrs = {
        "__tablename__": dist_table,
        "__mapper_args__": {"confirm_deleted_rows": False},
        "to_geojson": _orm_to_geojson,
    }
    if config.is_column_enabled("districts", "id"):
        dist_attrs["id"] = sa.Column(db_col("districts", "id"), sa.String(6), primary_key=True)
    if config.is_column_enabled("districts", "regency_id"):
        dist_attrs["regency_id"] = sa.Column(
            db_col("districts", "regency_id"), 
            sa.String(4), 
            sa.ForeignKey(f"{reg_table}.{db_col('regencies', 'id')}")
        )
    if config.is_column_enabled("districts", "name"):
        dist_attrs["name"] = sa.Column(db_col("districts", "name"), sa.String(100), nullable=False)
    if config.is_column_enabled("districts", "latitude"):
        dist_attrs["latitude"] = sa.Column(db_col("districts", "latitude"), sa.Float)
    if config.is_column_enabled("districts", "longitude"):
        dist_attrs["longitude"] = sa.Column(db_col("districts", "longitude"), sa.Float)
    if config.is_column_enabled("districts", "boundary"):
        dist_attrs["boundary"] = sa.Column(db_col("districts", "boundary"), boundary_type)

    # 5. Build Village Attributes
    vil_attrs = {
        "__tablename__": vil_table,
        "__mapper_args__": {"confirm_deleted_rows": False},
        "to_geojson": _orm_to_geojson,
    }
    if config.is_column_enabled("villages", "id"):
        vil_attrs["id"] = sa.Column(db_col("villages", "id"), sa.String(10), primary_key=True)
    if config.is_column_enabled("villages", "district_id"):
        vil_attrs["district_id"] = sa.Column(
            db_col("villages", "district_id"), 
            sa.String(6), 
            sa.ForeignKey(f"{dist_table}.{db_col('districts', 'id')}")
        )
    if config.is_column_enabled("villages", "name"):
        vil_attrs["name"] = sa.Column(db_col("villages", "name"), sa.String(100), nullable=False)
    if config.is_column_enabled("villages", "postal_code"):
        vil_attrs["postal_code"] = sa.Column(db_col("villages", "postal_code"), sa.String(10))
    if config.is_column_enabled("villages", "latitude"):
        vil_attrs["latitude"] = sa.Column(db_col("villages", "latitude"), sa.Float)
    if config.is_column_enabled("villages", "longitude"):
        vil_attrs["longitude"] = sa.Column(db_col("villages", "longitude"), sa.Float)
    if config.is_column_enabled("villages", "boundary"):
        vil_attrs["boundary"] = sa.Column(db_col("villages", "boundary"), boundary_type)

    # 6. Add Relationships
    prov_attrs["regencies"] = relationship("Regency", back_populates="province")
    prov_attrs["districts"] = relationship(
        "District",
        secondary=reg_table,
        primaryjoin=f"Province.id == Regency.province_id",
        secondaryjoin=f"Regency.id == District.regency_id",
        viewonly=True,
    )

    reg_attrs["province"] = relationship("Province", back_populates="regencies")
    reg_attrs["districts"] = relationship("District", back_populates="regency")
    reg_attrs["villages"] = relationship(
        "Village",
        secondary=dist_table,
        primaryjoin=f"Regency.id == District.regency_id",
        secondaryjoin=f"District.id == Village.district_id",
        viewonly=True,
    )

    dist_attrs["regency"] = relationship("Regency", back_populates="districts")
    dist_attrs["villages"] = relationship("Village", back_populates="district")

    vil_attrs["district"] = relationship("District", back_populates="villages")

    # 7. Generate Classes
    Province = type("Province", (base_class,), prov_attrs)
    Regency = type("Regency", (base_class,), reg_attrs)
    District = type("District", (base_class,), dist_attrs)
    Village = type("Village", (base_class,), vil_attrs)

    return {
        "Province": Province,
        "Regency": Regency,
        "District": District,
        "Village": Village,
    }


class NusantaraSeeder:
    """Streams gzipped CSV files and bulk inserts them into a database using SQLAlchemy."""

    def __init__(self, session: Any, config: NusantaraConfig, reader: NusantaraReader):
        self.session = session
        self.config = config
        self.reader = reader

    def seed(self, batch_size: int = 500, progress_callback: Optional[Any] = None) -> None:
        """Execute database seeding in order: Provinces, Regencies, Districts, Villages.
        
        Args:
            batch_size: Bulk insert chunk size.
            progress_callback: Callback function called as: callback(stage_name, processed_rows_count).
        """
        logger.info("Starting database seeding...")
        from sqlalchemy.orm import declarative_base
        TempBase = declarative_base()
        models = build_models(TempBase, self.config)
        
        # 1. Seed Provinces
        if progress_callback:
            progress_callback("provinces_start", 0)
        prov_records = self.reader.read_provinces()
        self._bulk_insert(models["Province"], prov_records, batch_size)
        if progress_callback:
            progress_callback("provinces_end", len(prov_records))

        # 2. Seed Regencies
        if progress_callback:
            progress_callback("regencies_start", 0)
        reg_records = self.reader.read_regencies()
        self._bulk_insert(models["Regency"], reg_records, batch_size)
        if progress_callback:
            progress_callback("regencies_end", len(reg_records))

        # 3. Seed Districts
        if progress_callback:
            progress_callback("districts_start", 0)
        dist_records = self.reader.read_districts()
        self._bulk_insert(models["District"], dist_records, batch_size)
        if progress_callback:
            progress_callback("districts_end", len(dist_records))

        # 4. Seed Villages
        if progress_callback:
            progress_callback("villages_start", 0)
        
        village_batch = []
        total_villages = 0
        for village in self.reader.stream_all_villages():
            village_batch.append(village)
            if len(village_batch) >= batch_size:
                self._bulk_insert(models["Village"], village_batch, batch_size)
                total_villages += len(village_batch)
                if progress_callback:
                    progress_callback("villages_progress", total_villages)
                village_batch = []
        
        if village_batch:
            self._bulk_insert(models["Village"], village_batch, batch_size)
            total_villages += len(village_batch)
            
        if progress_callback:
            progress_callback("villages_end", total_villages)
        logger.info("Database seeding completed.")

    def _bulk_insert(self, model_class: Any, records: List[Dict[str, Any]], batch_size: int) -> None:
        """Perform bulk insertion using SQLAlchemy Core inserts for speed."""
        if not records:
            return

        table = model_class.__table__
        logger.info(f"Bulk inserting {len(records)} records into {table.name}...")
        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            self.session.execute(sa.insert(table), chunk)
        self.session.commit()

    def seed_boundaries(
        self,
        levels: List[str] = ["provinces", "regencies", "districts", "villages"],
        force: bool = False,
        cache_dir: Optional[Union[str, Path]] = None,
        batch_size: int = 200,
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Update database records with geographic boundary coordinates from local cache.
        
        Requires download_boundaries() to be executed first to populate the cache.
        """
        # Resolve cache dir
        boundaries_cfg = self.config._config.get("boundaries", {})
        local_path = boundaries_cfg.get("local_path")
        if cache_dir:
            resolved_cache_dir = Path(cache_dir)
        elif local_path:
            resolved_cache_dir = Path(local_path)
        else:
            resolved_cache_dir = get_default_cache_dir()

        storage_type = boundaries_cfg.get("type", "spatial")
        verify_checksum = boundaries_cfg.get("verify_checksum", True)
        engine = self.session.bind
        driver_name = engine.dialect.name

        placeholder = "ST_GeomFromText(:wkt)"
        if "mssql" in driver_name:
            placeholder = "geometry::STGeomFromText(:wkt, 4326)"
        elif "postgresql" in driver_name:
            placeholder = "ST_GeomFromText(:wkt, 4326)"

        logger.info(f"Seeding boundaries from cache directory: {resolved_cache_dir}")

        for level in levels:
            table_name = self.config.get_table_name(level)
            id_col = self.config.resolve_column_name(level, "id")
            boundary_col = self.config.resolve_column_name(level, "boundary")

            if not self.config.is_column_enabled(level, "boundary"):
                continue

            if progress_callback:
                progress_callback("seed_boundaries_start", level)

            # Resolve boundary file paths
            if level == "villages":
                from py_nusantara.manifest import Manifest
                village_files = sorted([k for k in Manifest.HASHES.keys() if k.startswith("villages_")])
                total_villages = 0
                for filename in village_files:
                    filepath = resolved_cache_dir / filename
                    if not filepath.exists():
                        continue
                    
                    if verify_checksum:
                        Manifest.verify(filepath)

                    seeded = self._seed_boundary_file(
                        filepath, table_name, id_col, boundary_col,
                        storage_type, placeholder, force, batch_size
                    )
                    total_villages += seeded
                    if progress_callback:
                        progress_callback("seed_boundaries_progress", f"villages: {total_villages}")
                if progress_callback:
                    progress_callback("seed_boundaries_end", f"villages: {total_villages}")
            else:
                filename = f"{level}.csv.gz"
                filepath = resolved_cache_dir / filename
                if not filepath.exists():
                    raise DataNotFoundError(f"Boundary file not found in cache: {filepath}. Run download_boundaries first.")

                if verify_checksum:
                    from py_nusantara.manifest import Manifest
                    Manifest.verify(filepath)

                seeded = self._seed_boundary_file(
                    filepath, table_name, id_col, boundary_col,
                    storage_type, placeholder, force, batch_size
                )
                if progress_callback:
                    progress_callback("seed_boundaries_end", f"{level}: {seeded}")

    def _seed_boundary_file(
        self,
        filepath: Path,
        table_name: str,
        id_col: str,
        boundary_col: str,
        storage_type: str,
        placeholder: str,
        force: bool,
        batch_size: int,
    ) -> int:
        """Seed a single boundary file, returning number of records updated."""
        seeded_count = 0
        batch_params = []

        # Form SQL statement with conditional updates for non-forced runs (N+1 query optimization)
        where_clause = f"WHERE {id_col} = :id"
        if not force:
            where_clause += f" AND {boundary_col} IS NULL"

        if storage_type == "spatial":
            sql = f"UPDATE {table_name} SET {boundary_col} = {placeholder} {where_clause}"
        else:
            sql = f"UPDATE {table_name} SET {boundary_col} = :boundary {where_clause}"

        stmt = sa.text(sql)

        with gzip.open(filepath, "rt", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                return 0

            for row in reader:
                if len(headers) != len(row):
                    continue
                record = dict(zip(headers, row))
                row_id = record.get("id")
                boundary_json = record.get("boundary")

                if not row_id or not boundary_json:
                    continue

                if storage_type == "spatial":
                    wkt = json_to_wkt(boundary_json)
                    if wkt:
                        batch_params.append({"wkt": wkt, "id": row_id})
                else:
                    batch_params.append({"boundary": boundary_json, "id": row_id})

                if len(batch_params) >= batch_size:
                    self.session.execute(stmt, batch_params)
                    self.session.commit()
                    seeded_count += len(batch_params)
                    batch_params = []

            if batch_params:
                self.session.execute(stmt, batch_params)
                self.session.commit()
                seeded_count += len(batch_params)

        return seeded_count

    async def seed_async(self, batch_size: int = 500, progress_callback: Optional[Any] = None) -> None:
        """Execute database seeding asynchronously in order: Provinces, Regencies, Districts, Villages.
        
        Args:
            batch_size: Bulk insert chunk size.
            progress_callback: Callback function called as: callback(stage_name, processed_rows_count).
        """
        logger.info("Starting database seeding asynchronously...")
        from sqlalchemy.orm import declarative_base
        TempBase = declarative_base()
        models = build_models(TempBase, self.config)
        
        # 1. Seed Provinces
        if progress_callback:
            progress_callback("provinces_start", 0)
        prov_records = self.reader.read_provinces()
        await self._bulk_insert_async(models["Province"], prov_records, batch_size)
        if progress_callback:
            progress_callback("provinces_end", len(prov_records))

        # 2. Seed Regencies
        if progress_callback:
            progress_callback("regencies_start", 0)
        reg_records = self.reader.read_regencies()
        await self._bulk_insert_async(models["Regency"], reg_records, batch_size)
        if progress_callback:
            progress_callback("regencies_end", len(reg_records))

        # 3. Seed Districts
        if progress_callback:
            progress_callback("districts_start", 0)
        dist_records = self.reader.read_districts()
        await self._bulk_insert_async(models["District"], dist_records, batch_size)
        if progress_callback:
            progress_callback("districts_end", len(dist_records))

        # 4. Seed Villages
        if progress_callback:
            progress_callback("villages_start", 0)
        
        village_batch = []
        total_villages = 0
        for village in self.reader.stream_all_villages():
            village_batch.append(village)
            if len(village_batch) >= batch_size:
                await self._bulk_insert_async(models["Village"], village_batch, batch_size)
                total_villages += len(village_batch)
                if progress_callback:
                    progress_callback("villages_progress", total_villages)
                village_batch = []
        
        if village_batch:
            await self._bulk_insert_async(models["Village"], village_batch, batch_size)
            total_villages += len(village_batch)
            
        if progress_callback:
            progress_callback("villages_end", total_villages)
        logger.info("Database seeding asynchronously completed.")

    async def _bulk_insert_async(self, model_class: Any, records: List[Dict[str, Any]], batch_size: int) -> None:
        """Perform bulk insertion asynchronously using SQLAlchemy Core inserts for speed."""
        if not records:
            return

        table = model_class.__table__
        logger.info(f"Bulk inserting {len(records)} records asynchronously into {table.name}...")
        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            await self.session.execute(sa.insert(table), chunk)
        await self.session.commit()

    async def seed_boundaries_async(
        self,
        levels: List[str] = ["provinces", "regencies", "districts", "villages"],
        force: bool = False,
        cache_dir: Optional[Union[str, Path]] = None,
        batch_size: int = 200,
        progress_callback: Optional[Any] = None,
    ) -> None:
        """Update database records with geographic boundary coordinates from local cache asynchronously.
        
        Requires download_boundaries() to be executed first to populate the cache.
        """
        # Resolve cache dir
        boundaries_cfg = self.config._config.get("boundaries", {})
        local_path = boundaries_cfg.get("local_path")
        if cache_dir:
            resolved_cache_dir = Path(cache_dir)
        elif local_path:
            resolved_cache_dir = Path(local_path)
        else:
            resolved_cache_dir = get_default_cache_dir()

        storage_type = boundaries_cfg.get("type", "spatial")
        verify_checksum = boundaries_cfg.get("verify_checksum", True)
        
        bind = self.session.bind
        if hasattr(bind, "sync_engine"):
            driver_name = bind.sync_engine.dialect.name
        else:
            driver_name = bind.dialect.name

        placeholder = "ST_GeomFromText(:wkt)"
        if "mssql" in driver_name:
            placeholder = "geometry::STGeomFromText(:wkt, 4326)"
        elif "postgresql" in driver_name:
            placeholder = "ST_GeomFromText(:wkt, 4326)"

        logger.info(f"Seeding boundaries asynchronously from cache directory: {resolved_cache_dir}")

        for level in levels:
            table_name = self.config.get_table_name(level)
            id_col = self.config.resolve_column_name(level, "id")
            boundary_col = self.config.resolve_column_name(level, "boundary")

            if not self.config.is_column_enabled(level, "boundary"):
                continue

            if progress_callback:
                progress_callback("seed_boundaries_start", level)

            # Resolve boundary file paths
            if level == "villages":
                from py_nusantara.manifest import Manifest
                village_files = sorted([k for k in Manifest.HASHES.keys() if k.startswith("villages_")])
                total_villages = 0
                for filename in village_files:
                    filepath = resolved_cache_dir / filename
                    if not filepath.exists():
                        continue
                    
                    if verify_checksum:
                        Manifest.verify(filepath)

                    seeded = await self._seed_boundary_file_async(
                        filepath, table_name, id_col, boundary_col,
                        storage_type, placeholder, force, batch_size
                    )
                    total_villages += seeded
                    if progress_callback:
                        progress_callback("seed_boundaries_progress", f"villages: {total_villages}")
                if progress_callback:
                    progress_callback("seed_boundaries_end", f"villages: {total_villages}")
            else:
                filename = f"{level}.csv.gz"
                filepath = resolved_cache_dir / filename
                if not filepath.exists():
                    raise DataNotFoundError(f"Boundary file not found in cache: {filepath}. Run download_boundaries first.")

                if verify_checksum:
                    from py_nusantara.manifest import Manifest
                    Manifest.verify(filepath)

                seeded = await self._seed_boundary_file_async(
                    filepath, table_name, id_col, boundary_col,
                    storage_type, placeholder, force, batch_size
                )
                if progress_callback:
                    progress_callback("seed_boundaries_end", f"{level}: {seeded}")

    async def _seed_boundary_file_async(
        self,
        filepath: Path,
        table_name: str,
        id_col: str,
        boundary_col: str,
        storage_type: str,
        placeholder: str,
        force: bool,
        batch_size: int,
    ) -> int:
        """Seed a single boundary file asynchronously, returning number of records updated."""
        seeded_count = 0
        batch_params = []

        # Form SQL statement with conditional updates for non-forced runs (N+1 query optimization)
        where_clause = f"WHERE {id_col} = :id"
        if not force:
            where_clause += f" AND {boundary_col} IS NULL"

        if storage_type == "spatial":
            sql = f"UPDATE {table_name} SET {boundary_col} = {placeholder} {where_clause}"
        else:
            sql = f"UPDATE {table_name} SET {boundary_col} = :boundary {where_clause}"

        stmt = sa.text(sql)

        with gzip.open(filepath, "rt", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                return 0

            for row in reader:
                if len(headers) != len(row):
                    continue
                record = dict(zip(headers, row))
                row_id = record.get("id")
                boundary_json = record.get("boundary")

                if not row_id or not boundary_json:
                    continue

                if storage_type == "spatial":
                    wkt = json_to_wkt(boundary_json)
                    if wkt:
                        batch_params.append({"wkt": wkt, "id": row_id})
                else:
                    batch_params.append({"boundary": boundary_json, "id": row_id})

                if len(batch_params) >= batch_size:
                    await self.session.execute(stmt, batch_params)
                    await self.session.commit()
                    seeded_count += len(batch_params)
                    batch_params = []

            if batch_params:
                await self.session.execute(stmt, batch_params)
                await self.session.commit()
                seeded_count += len(batch_params)

        return seeded_count

