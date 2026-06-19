from typing import Any, Dict, List, Optional
from py_nusantara.config import NusantaraConfig
from py_nusantara.reader import NusantaraReader


class NusantaraSearch:
    """Handles query searching across administrative levels for the CSV direct-access mode."""

    def __init__(self, config: NusantaraConfig, reader: NusantaraReader):
        self.config = config
        self.reader = reader

    def search(
        self, query: str, limit: int = 20, scope: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search for regional names matching a query string (case-insensitive substring match).
        
        Supports a scope dictionary (province_id, regency_id, district_id) to filter search results.
        Returns a dictionary with matching records for each level up to the limit.
        """
        query = query.strip()
        if len(query) < 2:
            return {
                "provinces": [],
                "regencies": [],
                "districts": [],
                "villages": [],
            }

        q_lower = query.lower()
        scope = scope or {}
        scope_prov = scope.get("province_id")
        scope_reg = scope.get("regency_id")
        scope_dist = scope.get("district_id")

        # Resolve logical column names
        prov_id_col = self.config.resolve_column_name("provinces", "id")
        prov_name_col = self.config.resolve_column_name("provinces", "name")

        reg_id_col = self.config.resolve_column_name("regencies", "id")
        reg_prov_id_col = self.config.resolve_column_name("regencies", "province_id")
        reg_name_col = self.config.resolve_column_name("regencies", "name")

        dist_id_col = self.config.resolve_column_name("districts", "id")
        dist_reg_id_col = self.config.resolve_column_name("districts", "regency_id")
        dist_name_col = self.config.resolve_column_name("districts", "name")

        vil_dist_id_col = self.config.resolve_column_name("villages", "district_id")
        vil_name_col = self.config.resolve_column_name("villages", "name")

        results: Dict[str, List[Dict[str, Any]]] = {
            "provinces": [],
            "regencies": [],
            "districts": [],
            "villages": [],
        }

        # 1. Search Provinces (Only search if scope is not constrained below province level)
        if not scope_reg and not scope_dist:
            for p in self.reader.read_provinces():
                p_id = p.get(prov_id_col)
                if scope_prov and p_id != scope_prov:
                    continue
                name_val = p.get(prov_name_col)
                if name_val and q_lower in name_val.lower():
                    results["provinces"].append(p)
                    if len(results["provinces"]) >= limit:
                        break

        # 2. Search Regencies (Only search if scope is not constrained below regency level)
        if not scope_dist:
            for r in self.reader.read_regencies():
                r_id = r.get(reg_id_col)
                if scope_reg and r_id != scope_reg:
                    continue
                if scope_prov and r.get(reg_prov_id_col) != scope_prov:
                    continue
                name_val = r.get(reg_name_col)
                if name_val and q_lower in name_val.lower():
                    results["regencies"].append(r)
                    if len(results["regencies"]) >= limit:
                        break

        # 3. Search Districts
        for d in self.reader.read_districts():
            d_id = d.get(dist_id_col) or ""
            if scope_dist and d_id != scope_dist:
                continue
            if scope_reg and d.get(dist_reg_id_col) != scope_reg:
                continue
            if scope_prov and not d_id.startswith(scope_prov):
                continue
            name_val = d.get(dist_name_col)
            if name_val and q_lower in name_val.lower():
                results["districts"].append(d)
                if len(results["districts"]) >= limit:
                    break

        # 4. Search Villages (Optimize read using partitions if scoped)
        if scope_dist:
            villages_source = self.reader.read_villages(district_id=scope_dist)
        elif scope_reg:
            villages_source = self.reader.read_villages(province_id=scope_reg[:2])
        elif scope_prov:
            villages_source = self.reader.read_villages(province_id=scope_prov)
        else:
            villages_source = self.reader.stream_all_villages()

        for v in villages_source:
            v_dist = v.get(vil_dist_id_col) or ""
            if scope_dist and v_dist != scope_dist:
                continue
            if scope_reg and not v_dist.startswith(scope_reg):
                continue
            if scope_prov and not v_dist.startswith(scope_prov):
                continue
            name_val = v.get(vil_name_col)
            if name_val and q_lower in name_val.lower():
                results["villages"].append(v)
                if len(results["villages"]) >= limit:
                    break

        return results

