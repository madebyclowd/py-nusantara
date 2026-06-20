import math
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from py_nusantara.records import BaseRecord, ProvinceRecord, RegencyRecord, DistrictRecord, VillageRecord
from py_nusantara.historical import resolve_legacy_id
from py_nusantara.spatial import haversine_distance

logger = logging.getLogger("py_nusantara")

try:
    import sqlalchemy as sa
    from sqlalchemy.orm import relationship, sessionmaker
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class QueryAdapter(ABC):
    """Abstract Base Class for Nusantara query engines."""

    @abstractmethod
    def provinces(self) -> List[ProvinceRecord]:
        pass

    @abstractmethod
    def find_province(self, id: str) -> Optional[ProvinceRecord]:
        pass

    @abstractmethod
    def regencies_of(self, province_id: str) -> List[RegencyRecord]:
        pass

    @abstractmethod
    def find_regency(self, id: str) -> Optional[RegencyRecord]:
        pass

    @abstractmethod
    def districts_of(self, regency_id: str) -> List[DistrictRecord]:
        pass

    @abstractmethod
    def find_district(self, id: str) -> Optional[DistrictRecord]:
        pass

    @abstractmethod
    def villages_of(self, district_id: str) -> List[VillageRecord]:
        pass

    @abstractmethod
    def villages_of_province(self, province_id: str) -> List[VillageRecord]:
        pass

    @abstractmethod
    def find_village(self, id: str) -> Optional[VillageRecord]:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def find_by_coordinate(
        self,
        latitude: float,
        longitude: float,
        fallback_to_nearest: bool = True,
    ) -> Dict[str, Optional[BaseRecord]]:
        pass

    @abstractmethod
    def find_nearby(
        self, latitude: float, longitude: float, radius_km: float, level: str = "villages"
    ) -> List[BaseRecord]:
        pass

    @abstractmethod
    def find_knn(
        self, latitude: float, longitude: float, k: int = 5, level: str = "villages"
    ) -> List[BaseRecord]:
        pass

    @abstractmethod
    def find_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        level: str = "villages",
        use_boundary: bool = False,
    ) -> List[BaseRecord]:
        pass

    @abstractmethod
    def find_adjacent(
        self,
        record: BaseRecord,
        level: Optional[str] = None,
    ) -> List[BaseRecord]:
        pass


class InMemoryQueryAdapter(QueryAdapter):
    """CSV direct-access in-memory query engine adapter."""

    def __init__(self, facade: Any) -> None:
        self.facade = facade
        self.config = facade.config
        self.reader = facade.reader

    def provinces(self) -> List[ProvinceRecord]:
        raw = self.facade._get_shared_data(
            "provinces_dataset",
            lambda: self.reader.read_provinces()
        )
        return [ProvinceRecord(r, self.config, self.facade) for r in raw]

    def find_province(self, id: str) -> Optional[ProvinceRecord]:
        id_col = self.config.resolve_column_name("provinces", "id")
        for p in self.provinces():
            if getattr(p, id_col) == id:
                return p
        return None

    def regencies_of(self, province_id: str) -> List[RegencyRecord]:
        prov_id_col = self.config.resolve_column_name("regencies", "province_id")
        raw = self.facade._get_shared_data(
            "regencies_dataset",
            lambda: self.reader.read_regencies()
        )
        return [
            RegencyRecord(r, self.config, self.facade)
            for r in raw
            if r.get(prov_id_col) == province_id
        ]

    def find_regency(self, id: str) -> Optional[RegencyRecord]:
        prov_id = id[:2]
        id_col = self.config.resolve_column_name("regencies", "id")
        for r in self.regencies_of(prov_id):
            if getattr(r, id_col) == id:
                return r
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_regency(active_id)
        return None

    def districts_of(self, regency_id: str) -> List[DistrictRecord]:
        reg_id_col = self.config.resolve_column_name("districts", "regency_id")
        raw = self.facade._get_shared_data(
            "districts_dataset",
            lambda: self.reader.read_districts()
        )
        return [
            DistrictRecord(r, self.config, self.facade)
            for r in raw
            if r.get(reg_id_col) == regency_id
        ]

    def find_district(self, id: str) -> Optional[DistrictRecord]:
        reg_id = id[:4]
        id_col = self.config.resolve_column_name("districts", "id")
        for d in self.districts_of(reg_id):
            if getattr(d, id_col) == id:
                return d
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_district(active_id)
        return None

    def villages_of(self, district_id: str) -> List[VillageRecord]:
        prov_id = district_id[:2]
        raw = self.facade._get_shared_data(
            f"villages_dataset_{prov_id}",
            lambda: self.reader.read_villages(province_id=prov_id)
        )
        dist_id_col = self.config.resolve_column_name("villages", "district_id")
        return [
            VillageRecord(r, self.config, self.facade)
            for r in raw
            if r.get(dist_id_col) == district_id
        ]

    def villages_of_province(self, province_id: str) -> List[VillageRecord]:
        raw = self.facade._get_shared_data(
            f"villages_dataset_{province_id}",
            lambda: self.reader.read_villages(province_id=province_id)
        )
        return [VillageRecord(r, self.config, self.facade) for r in raw]

    def find_village(self, id: str) -> Optional[VillageRecord]:
        dist_id = id[:6]
        id_col = self.config.resolve_column_name("villages", "id")
        for v in self.villages_of(dist_id):
            if getattr(v, id_col) == id:
                return v
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_village(active_id)
        return None

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
        raw_res = self.facade.searcher.search(
            query,
            limit=limit,
            offset=offset,
            cursor=cursor,
            scope=scope,
            fuzzy=fuzzy,
            threshold=threshold,
            similarity_method=similarity_method,
        )
        return {
            "provinces": [ProvinceRecord(r, self.config, self.facade) for r in raw_res["provinces"]],
            "regencies": [RegencyRecord(r, self.config, self.facade) for r in raw_res["regencies"]],
            "districts": [DistrictRecord(r, self.config, self.facade) for r in raw_res["districts"]],
            "villages": [VillageRecord(r, self.config, self.facade) for r in raw_res["villages"]],
        }

    def find_by_coordinate(
        self,
        latitude: float,
        longitude: float,
        fallback_to_nearest: bool = True,
    ) -> Dict[str, Optional[BaseRecord]]:
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
        from py_nusantara.spatial import is_point_in_boundary
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

    def find_nearby(
        self, latitude: float, longitude: float, radius_km: float, level: str = "villages"
    ) -> List[BaseRecord]:
        return self.facade.find_nearby(latitude, longitude, radius_km, level=level)

    def find_knn(
        self, latitude: float, longitude: float, k: int = 5, level: str = "villages"
    ) -> List[BaseRecord]:
        return self.facade.find_knn(latitude, longitude, k=k, level=level)

    def find_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        level: str = "villages",
        use_boundary: bool = False,
    ) -> List[BaseRecord]:
        return self.facade._execute_find_in_bbox(min_lat, min_lon, max_lat, max_lon, level, use_boundary)

    def find_adjacent(
        self,
        record: BaseRecord,
        level: Optional[str] = None,
    ) -> List[BaseRecord]:
        target_level = level or record._level
        if target_level not in ("provinces", "regencies", "districts", "villages"):
            raise ValueError("level must be one of: provinces, regencies, districts, villages")
            
        boundary_val = getattr(record, "boundary", None)
        if not boundary_val:
            return []

        try:
            import shapely.geometry
            from py_nusantara.spatial import parse_boundary_to_geojson_geometry
        except ImportError:
            raise ImportError("shapely is required to find adjacent regions.")

        geojson_geom = parse_boundary_to_geojson_geometry(boundary_val)
        if not geojson_geom:
            return []
        query_shape = shapely.geometry.shape(geojson_geom)

        candidates = []
        if target_level == "provinces":
            candidates = self.provinces()
        elif target_level == "regencies":
            raw = self.facade._get_shared_data("regencies_dataset", lambda: self.reader.read_regencies())
            candidates = [RegencyRecord(r, self.config, self.facade) for r in raw]
        elif target_level == "districts":
            raw = self.facade._get_shared_data("districts_dataset", lambda: self.reader.read_districts())
            candidates = [DistrictRecord(r, self.config, self.facade) for r in raw]
        elif target_level == "villages":
            # Optimization: only check villages of same province to avoid O(N) boundary geometry parsing
            prov_id = record.id[:2]
            candidates = self.villages_of_province(prov_id)

        results = []
        for cand in candidates:
            if cand.id == record.id and target_level == record._level:
                continue
            cand_boundary = getattr(cand, "boundary", None)
            if cand_boundary:
                cand_geom = parse_boundary_to_geojson_geometry(cand_boundary)
                if cand_geom:
                    cand_shape = shapely.geometry.shape(cand_geom)
                    if query_shape.touches(cand_shape):
                        results.append(cand)
        return results


class DatabaseQueryAdapter(QueryAdapter):
    """Database-backed SQL compiling query engine adapter using SQLAlchemy."""

    def __init__(self, facade: Any, engine_or_session: Any, models: Optional[Dict[str, Any]] = None) -> None:
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError(
                "SQLAlchemy is required to use DatabaseQueryAdapter. "
                "Install it via: pip install py-nusantara[sqlalchemy]"
            )
        self.facade = facade
        self.config = facade.config
        self.engine_or_session = engine_or_session

        # Resolve dialect name
        bind = getattr(engine_or_session, "bind", None)
        if bind is None:
            if hasattr(engine_or_session, "connection"):
                try:
                    bind = engine_or_session.connection()
                except Exception:
                    pass
            if bind is None:
                bind = engine_or_session

        if hasattr(bind, "sync_engine"):
            self.dialect_name = bind.sync_engine.dialect.name
        else:
            self.dialect_name = getattr(getattr(bind, "dialect", None), "name", "unknown")

        # Resolve models
        if models:
            self.models = models
        else:
            from py_nusantara.db import build_models
            from sqlalchemy.orm import declarative_base
            TempBase = declarative_base()
            self.models = build_models(TempBase, self.config)

    def _execute_stmt(self, stmt: Any) -> List[Any]:
        from sqlalchemy.orm import Session
        if isinstance(self.engine_or_session, Session) or hasattr(self.engine_or_session, "scalar"):
            session = self.engine_or_session
            try:
                return session.scalars(stmt).all()
            except AttributeError:
                return [row[0] for row in session.execute(stmt).all()]
        else:
            # We bind transient session
            from sqlalchemy.orm import Session as ORMSession
            with ORMSession(bind=self.engine_or_session) as session:
                try:
                    return session.scalars(stmt).all()
                except AttributeError:
                    return [row[0] for row in session.execute(stmt).all()]

    def _to_record(self, orm_instance: Any, level: str) -> BaseRecord:
        data = {}
        for logical_name, col_cfg in self.config.get_columns(level).items():
            if col_cfg.get("enabled", False):
                db_name = col_cfg.get("name", logical_name)
                val = getattr(orm_instance, db_name, None)
                data[db_name] = val
        
        if hasattr(orm_instance, "distance_km"):
            data["distance_km"] = orm_instance.distance_km

        if level == "provinces":
            return ProvinceRecord(data, self.config, self.facade)
        elif level == "regencies":
            return RegencyRecord(data, self.config, self.facade)
        elif level == "districts":
            return DistrictRecord(data, self.config, self.facade)
        elif level == "villages":
            return VillageRecord(data, self.config, self.facade)
        return BaseRecord(data, self.config, self.facade)

    def provinces(self) -> List[ProvinceRecord]:
        model = self.models["Province"]
        stmt = sa.select(model)
        if self.config.is_column_enabled("provinces", "name"):
            stmt = stmt.order_by(model.name)
        results = self._execute_stmt(stmt)
        return [self._to_record(r, "provinces") for r in results]

    def find_province(self, id: str) -> Optional[ProvinceRecord]:
        model = self.models["Province"]
        stmt = sa.select(model).where(model.id == id)
        results = self._execute_stmt(stmt)
        if results:
            return self._to_record(results[0], "provinces")
        return None

    def regencies_of(self, province_id: str) -> List[RegencyRecord]:
        model = self.models["Regency"]
        stmt = sa.select(model).where(model.province_id == province_id)
        if self.config.is_column_enabled("regencies", "name"):
            stmt = stmt.order_by(model.name)
        results = self._execute_stmt(stmt)
        return [self._to_record(r, "regencies") for r in results]

    def find_regency(self, id: str) -> Optional[RegencyRecord]:
        model = self.models["Regency"]
        stmt = sa.select(model).where(model.id == id)
        results = self._execute_stmt(stmt)
        if results:
            return self._to_record(results[0], "regencies")
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_regency(active_id)
        return None

    def districts_of(self, regency_id: str) -> List[DistrictRecord]:
        model = self.models["District"]
        stmt = sa.select(model).where(model.regency_id == regency_id)
        if self.config.is_column_enabled("districts", "name"):
            stmt = stmt.order_by(model.name)
        results = self._execute_stmt(stmt)
        return [self._to_record(r, "districts") for r in results]

    def find_district(self, id: str) -> Optional[DistrictRecord]:
        model = self.models["District"]
        stmt = sa.select(model).where(model.id == id)
        results = self._execute_stmt(stmt)
        if results:
            return self._to_record(results[0], "districts")
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_district(active_id)
        return None

    def villages_of(self, district_id: str) -> List[VillageRecord]:
        model = self.models["Village"]
        stmt = sa.select(model).where(model.district_id == district_id)
        if self.config.is_column_enabled("villages", "name"):
            stmt = stmt.order_by(model.name)
        results = self._execute_stmt(stmt)
        return [self._to_record(r, "villages") for r in results]

    def villages_of_province(self, province_id: str) -> List[VillageRecord]:
        model = self.models["Village"]
        stmt = sa.select(model).where(model.id.like(f"{province_id}%"))
        if self.config.is_column_enabled("villages", "name"):
            stmt = stmt.order_by(model.name)
        results = self._execute_stmt(stmt)
        return [self._to_record(r, "villages") for r in results]

    def find_village(self, id: str) -> Optional[VillageRecord]:
        model = self.models["Village"]
        stmt = sa.select(model).where(model.id == id)
        results = self._execute_stmt(stmt)
        if results:
            return self._to_record(results[0], "villages")
        active_id = resolve_legacy_id(id)
        if active_id != id:
            return self.find_village(active_id)
        return None

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
        scope = scope or {}
        scope_prov = scope.get("province_id")
        scope_reg = scope.get("regency_id")
        scope_dist = scope.get("district_id")

        results = {
            "provinces": [],
            "regencies": [],
            "districts": [],
            "villages": [],
        }

        def _get_filter_expr(model, q):
            if fuzzy and "postgresql" in self.dialect_name:
                return sa.func.similarity(model.name, q) >= threshold
            else:
                return model.name.ilike(f"%{q}%")

        def _apply_ordering(stmt, model, q):
            if fuzzy and "postgresql" in self.dialect_name:
                return stmt.order_by(sa.func.similarity(model.name, q).desc())
            elif self.config.is_column_enabled(model.__tablename__, "name"):
                return stmt.order_by(model.name)
            return stmt

        # 1. Search Provinces
        if not scope_reg and not scope_dist:
            model = self.models["Province"]
            stmt = sa.select(model).where(_get_filter_expr(model, query))
            if scope_prov:
                stmt = stmt.where(model.id == scope_prov)
            if cursor:
                stmt = stmt.where(model.id > cursor)
            stmt = _apply_ordering(stmt, model, query)
            if offset is not None:
                stmt = stmt.offset(offset)
            stmt = stmt.limit(limit)
            results["provinces"] = [self._to_record(r, "provinces") for r in self._execute_stmt(stmt)]

        # 2. Search Regencies
        if not scope_dist:
            model = self.models["Regency"]
            stmt = sa.select(model).where(_get_filter_expr(model, query))
            if scope_reg:
                stmt = stmt.where(model.id == scope_reg)
            elif scope_prov:
                stmt = stmt.where(model.province_id == scope_prov)
            if cursor:
                stmt = stmt.where(model.id > cursor)
            stmt = _apply_ordering(stmt, model, query)
            if offset is not None:
                stmt = stmt.offset(offset)
            stmt = stmt.limit(limit)
            results["regencies"] = [self._to_record(r, "regencies") for r in self._execute_stmt(stmt)]

        # 3. Search Districts
        model = self.models["District"]
        stmt = sa.select(model).where(_get_filter_expr(model, query))
        if scope_dist:
            stmt = stmt.where(model.id == scope_dist)
        elif scope_reg:
            stmt = stmt.where(model.regency_id == scope_reg)
        elif scope_prov:
            stmt = stmt.where(model.id.like(f"{scope_prov}%"))
        if cursor:
            stmt = stmt.where(model.id > cursor)
        stmt = _apply_ordering(stmt, model, query)
        if offset is not None:
            stmt = stmt.offset(offset)
        stmt = stmt.limit(limit)
        results["districts"] = [self._to_record(r, "districts") for r in self._execute_stmt(stmt)]

        # 4. Search Villages
        model = self.models["Village"]
        stmt = sa.select(model).where(_get_filter_expr(model, query))
        if scope_dist:
            stmt = stmt.where(model.district_id == scope_dist)
        elif scope_reg:
            stmt = stmt.where(model.district_id.like(f"{scope_reg}%"))
        elif scope_prov:
            stmt = stmt.where(model.district_id.like(f"{scope_prov}%"))
        if cursor:
            stmt = stmt.where(model.id > cursor)
        stmt = _apply_ordering(stmt, model, query)
        if offset is not None:
            stmt = stmt.offset(offset)
        stmt = stmt.limit(limit)
        results["villages"] = [self._to_record(r, "villages") for r in self._execute_stmt(stmt)]

        return results

    def find_by_coordinate(
        self,
        latitude: float,
        longitude: float,
        fallback_to_nearest: bool = True,
    ) -> Dict[str, Optional[BaseRecord]]:
        res: Dict[str, Optional[BaseRecord]] = {
            "province": None,
            "regency": None,
            "district": None,
            "village": None,
        }

        def _resolve_level(level: str, parent_filter: Optional[Any] = None) -> Optional[Any]:
            model = self.models[level[:-1].capitalize()] if level != "regencies" else self.models["Regency"]
            
            if self.config.is_column_enabled(level, "boundary") and (self.config.use_geoalchemy2 or "postgresql" in self.dialect_name):
                point = sa.func.ST_SetSRID(sa.func.ST_Point(longitude, latitude), 4326)
                stmt = sa.select(model).where(sa.func.ST_Contains(model.boundary, point))
                if parent_filter is not None:
                    stmt = stmt.where(parent_filter)
                matches = self._execute_stmt(stmt)
                if matches:
                    return matches[0]

            if fallback_to_nearest:
                point = sa.func.ST_SetSRID(sa.func.ST_Point(longitude, latitude), 4326)
                if self.config.use_geoalchemy2 or "postgresql" in self.dialect_name:
                    if self.config.is_column_enabled(level, "boundary"):
                        order_expr = sa.func.ST_Distance(model.boundary, point)
                    else:
                        centroid_point = sa.func.ST_SetSRID(sa.func.ST_Point(model.longitude, model.latitude), 4326)
                        order_expr = sa.func.ST_Distance(centroid_point, point)
                else:
                    order_expr = (model.latitude - latitude) * (model.latitude - latitude) + (model.longitude - longitude) * (model.longitude - longitude)
                
                stmt = sa.select(model)
                if parent_filter is not None:
                    stmt = stmt.where(parent_filter)
                stmt = stmt.order_by(order_expr).limit(1)
                matches = self._execute_stmt(stmt)
                if matches:
                    return matches[0]
            
            return None

        prov_orm = _resolve_level("provinces")
        if prov_orm:
            res["province"] = self._to_record(prov_orm, "provinces")

            reg_orm = _resolve_level("regencies", parent_filter=(self.models["Regency"].province_id == prov_orm.id))
            if reg_orm:
                res["regency"] = self._to_record(reg_orm, "regencies")

                dist_orm = _resolve_level("districts", parent_filter=(self.models["District"].regency_id == reg_orm.id))
                if dist_orm:
                    res["district"] = self._to_record(dist_orm, "districts")

                    vil_orm = _resolve_level("villages", parent_filter=(self.models["Village"].district_id == dist_orm.id))
                    if vil_orm:
                        res["village"] = self._to_record(vil_orm, "villages")
        
        return res

    def find_nearby(
        self, latitude: float, longitude: float, radius_km: float, level: str = "villages"
    ) -> List[BaseRecord]:
        model = self.models[level[:-1].capitalize()] if level != "regencies" else self.models["Regency"]
        
        if self.config.use_geoalchemy2 or "postgresql" in self.dialect_name:
            point = sa.func.ST_SetSRID(sa.func.ST_Point(longitude, latitude), 4326)
            if self.config.is_column_enabled(level, "boundary"):
                geom_expr = sa.cast(model.boundary, sa.Geography)
            else:
                centroid_point = sa.func.ST_SetSRID(sa.func.ST_Point(model.longitude, model.latitude), 4326)
                geom_expr = sa.cast(centroid_point, sa.Geography)
            point_expr = sa.cast(point, sa.Geography)
            
            stmt = sa.select(model).where(sa.func.ST_DWithin(geom_expr, point_expr, radius_km * 1000))
            stmt = stmt.order_by(sa.func.ST_Distance(geom_expr, point_expr))
            results = self._execute_stmt(stmt)
            
            records = []
            for r in results:
                rec = self._to_record(r, level)
                rec.distance_km = haversine_distance(latitude, longitude, rec.latitude, rec.longitude)
                records.append(rec)
            return records

        lat_delta = radius_km / 111.0
        cos_lat = math.cos(math.radians(latitude))
        lon_delta = radius_km / (111.0 * cos_lat) if cos_lat > 0.01 else 180.0
        
        stmt = sa.select(model).where(
            model.latitude.between(latitude - lat_delta, latitude + lat_delta) &
            model.longitude.between(longitude - lon_delta, longitude + lon_delta)
        )
        
        results = self._execute_stmt(stmt)
        records = []
        for r in results:
            rec = self._to_record(r, level)
            dist = haversine_distance(latitude, longitude, rec.latitude, rec.longitude)
            if dist <= radius_km:
                rec.distance_km = dist
                records.append(rec)
        
        records.sort(key=lambda x: getattr(x, "distance_km", 0.0))
        return records

    def find_knn(
        self, latitude: float, longitude: float, k: int = 5, level: str = "villages"
    ) -> List[BaseRecord]:
        model = self.models[level[:-1].capitalize()] if level != "regencies" else self.models["Regency"]
        point = sa.func.ST_SetSRID(sa.func.ST_Point(longitude, latitude), 4326)
        
        if self.config.use_geoalchemy2 or "postgresql" in self.dialect_name:
            if self.config.is_column_enabled(level, "boundary"):
                order_expr = model.boundary.op("<->")(point)
            else:
                centroid_point = sa.func.ST_SetSRID(sa.func.ST_Point(model.longitude, model.latitude), 4326)
                order_expr = centroid_point.op("<->")(point)
            
            stmt = sa.select(model).order_by(order_expr).limit(k)
        else:
            order_expr = (model.latitude - latitude) * (model.latitude - latitude) + (model.longitude - longitude) * (model.longitude - longitude)
            stmt = sa.select(model).order_by(order_expr).limit(k)

        results = self._execute_stmt(stmt)
        records = []
        for r in results:
            rec = self._to_record(r, level)
            rec.distance_km = haversine_distance(latitude, longitude, rec.latitude, rec.longitude)
            records.append(rec)
        return records

    def find_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        level: str = "villages",
        use_boundary: bool = False,
    ) -> List[BaseRecord]:
        model = self.models[level[:-1].capitalize()] if level != "regencies" else self.models["Regency"]
        
        min_lat, max_lat = min(min_lat, max_lat), max(min_lat, max_lat)

        if use_boundary and self.config.is_column_enabled(level, "boundary") and (self.config.use_geoalchemy2 or "postgresql" in self.dialect_name):
            if min_lon <= max_lon:
                envelope = sa.func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
                stmt = sa.select(model).where(sa.func.ST_Intersects(model.boundary, envelope))
            else:
                envelope1 = sa.func.ST_MakeEnvelope(min_lon, min_lat, 180.0, max_lat, 4326)
                envelope2 = sa.func.ST_MakeEnvelope(-180.0, min_lat, max_lon, max_lat, 4326)
                stmt = sa.select(model).where(sa.func.ST_Intersects(model.boundary, envelope1) | sa.func.ST_Intersects(model.boundary, envelope2))
            return [self._to_record(r, level) for r in self._execute_stmt(stmt)]

        if min_lon <= max_lon:
            lon_filter = model.longitude.between(min_lon, max_lon)
        else:
            lon_filter = (model.longitude >= min_lon) | (model.longitude <= max_lon)

        stmt = sa.select(model).where(
            model.latitude.between(min_lat, max_lat) & lon_filter
        )
        return [self._to_record(r, level) for r in self._execute_stmt(stmt)]

    def find_adjacent(
        self,
        record: BaseRecord,
        level: Optional[str] = None,
    ) -> List[BaseRecord]:
        target_level = level or record._level
        model = self.models[target_level[:-1].capitalize()] if target_level != "regencies" else self.models["Regency"]
        
        boundary_val = getattr(record, "boundary", None)
        if not boundary_val:
            return []

        if self.config.is_column_enabled(target_level, "boundary") and (self.config.use_geoalchemy2 or "postgresql" in self.dialect_name):
            from py_nusantara.downloader import json_to_wkt
            wkt_val = None
            if isinstance(boundary_val, str):
                if boundary_val.strip().startswith("["):
                    wkt_val = json_to_wkt(boundary_val)
                else:
                    wkt_val = boundary_val
            
            if wkt_val:
                geom_element = sa.func.ST_GeomFromText(wkt_val, 4326)
                stmt = sa.select(model).where(
                    (sa.func.ST_Touches(model.boundary, geom_element) | sa.func.ST_Intersects(model.boundary, geom_element)) &
                    (model.id != record.id)
                )
                results = self._execute_stmt(stmt)
                return [self._to_record(r, target_level) for r in results]

        # Fallback to in-memory filter
        stmt = sa.select(model)
        if target_level == "villages":
            prov_id = record.id[:2]
            stmt = stmt.where(model.id.like(f"{prov_id}%"))
            
        candidates = [self._to_record(r, target_level) for r in self._execute_stmt(stmt)]
        
        try:
            import shapely.geometry
            from py_nusantara.spatial import parse_boundary_to_geojson_geometry
        except ImportError:
            return []

        geojson_geom = parse_boundary_to_geojson_geometry(boundary_val)
        if not geojson_geom:
            return []
        query_shape = shapely.geometry.shape(geojson_geom)

        results = []
        for cand in candidates:
            if cand.id == record.id and target_level == record._level:
                continue
            cand_boundary = getattr(cand, "boundary", None)
            if cand_boundary:
                cand_geom = parse_boundary_to_geojson_geometry(cand_boundary)
                if cand_geom:
                    cand_shape = shapely.geometry.shape(cand_geom)
                    if query_shape.touches(cand_shape):
                        results.append(cand)
        return results
