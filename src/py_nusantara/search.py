from typing import Any, Dict, List, Optional
from py_nusantara.config import NusantaraConfig
from py_nusantara.reader import NusantaraReader


class NusantaraSearch:
    """Handles query searching across administrative levels for the CSV direct-access mode."""

    def __init__(self, config: NusantaraConfig, reader: NusantaraReader):
        self.config = config
        self.reader = reader

    def search(self, query: str, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """Search for regional names matching a query string (case-insensitive substring match).
        
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

        # Resolve logical 'name' column for each level
        prov_name_col = self.config.resolve_column_name("provinces", "name")
        reg_name_col = self.config.resolve_column_name("regencies", "name")
        dist_name_col = self.config.resolve_column_name("districts", "name")
        vil_name_col = self.config.resolve_column_name("villages", "name")

        results: Dict[str, List[Dict[str, Any]]] = {
            "provinces": [],
            "regencies": [],
            "districts": [],
            "villages": [],
        }

        # 1. Search Provinces
        for p in self.reader.read_provinces():
            name_val = p.get(prov_name_col)
            if name_val and q_lower in name_val.lower():
                results["provinces"].append(p)
                if len(results["provinces"]) >= limit:
                    break

        # 2. Search Regencies
        for r in self.reader.read_regencies():
            name_val = r.get(reg_name_col)
            if name_val and q_lower in name_val.lower():
                results["regencies"].append(r)
                if len(results["regencies"]) >= limit:
                    break

        # 3. Search Districts
        for d in self.reader.read_districts():
            name_val = d.get(dist_name_col)
            if name_val and q_lower in name_val.lower():
                results["districts"].append(d)
                if len(results["districts"]) >= limit:
                    break

        # 4. Search Villages (Stream to stop early)
        for v in self.reader.stream_all_villages():
            name_val = v.get(vil_name_col)
            if name_val and q_lower in name_val.lower():
                results["villages"].append(v)
                if len(results["villages"]) >= limit:
                    break

        return results
