from typing import Any, Dict, List, Optional
from py_nusantara.config import NusantaraConfig
from py_nusantara.reader import NusantaraReader
from py_nusantara.utils import string_similarity


class NusantaraSearch:
    """Handles query searching across administrative levels for the CSV direct-access mode."""

    def __init__(self, config: NusantaraConfig, reader: NusantaraReader):
        self.config = config
        self.reader = reader

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
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search for regional names matching a query string (fuzzy or case-insensitive substring match).
        
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

        vil_id_col = self.config.resolve_column_name("villages", "id")
        vil_dist_id_col = self.config.resolve_column_name("villages", "district_id")
        vil_name_col = self.config.resolve_column_name("villages", "name")

        results: Dict[str, List[Dict[str, Any]]] = {
            "provinces": [],
            "regencies": [],
            "districts": [],
            "villages": [],
        }

        # Helper for length pruning checks
        def _should_prune(c_name: str) -> bool:
            if not fuzzy:
                return False
            
            c_clean = c_name.lower().strip()
            for prefix in ("kabupaten ", "kota ", "kecamatan ", "kelurahan ", "desa ", "provinsi ", "daerah istimewa "):
                if c_clean.startswith(prefix):
                    c_clean = c_clean[len(prefix):].strip()
                    break
                    
            len_q = len(query)
            len_candidates = [len(c_clean)] + [len(w) for w in c_clean.split()]
            
            for len_c in len_candidates:
                if similarity_method == "trigram" and len_q >= 3 and len_c >= 3:
                    if min(len_q - 2, len_c - 2) >= threshold * max(len_q - 2, len_c - 2):
                        return False
                else:
                    if abs(len_q - len_c) <= max(len_q, len_c) * (1.0 - threshold):
                        return False
            return True


        # 1. Search Provinces (Only search if scope is not constrained below province level)
        if not scope_reg and not scope_dist:
            prov_candidates = []
            for p in self.reader.read_provinces():
                p_id = p.get(prov_id_col)
                if scope_prov and p_id != scope_prov:
                    continue
                name_val = p.get(prov_name_col)
                if not name_val:
                    continue
                
                if fuzzy:
                    if _should_prune(name_val):
                        continue
                    score = string_similarity(query, name_val, method=similarity_method)
                    if score >= threshold:
                        prov_candidates.append((score, p))
                else:
                    if q_lower in name_val.lower():
                        prov_candidates.append((1.0, p))
                        # We cannot break early if cursor or fuzzy sorting is active
                        if not cursor and len(prov_candidates) >= (offset or 0) + limit:
                            break
            
            if cursor:
                prov_candidates = [c for c in prov_candidates if c[1].get(prov_id_col) > cursor]
            if fuzzy:
                prov_candidates.sort(key=lambda x: x[0], reverse=True)
            start_idx = offset or 0
            results["provinces"] = [c[1] for c in prov_candidates[start_idx : start_idx + limit]]

        # 2. Search Regencies (Only search if scope is not constrained below regency level)
        if not scope_dist:
            reg_candidates = []
            for r in self.reader.read_regencies():
                r_id = r.get(reg_id_col)
                if scope_reg and r_id != scope_reg:
                    continue
                if scope_prov and r.get(reg_prov_id_col) != scope_prov:
                    continue
                name_val = r.get(reg_name_col)
                if not name_val:
                    continue
                
                if fuzzy:
                    if _should_prune(name_val):
                        continue
                    score = string_similarity(query, name_val, method=similarity_method)
                    if score >= threshold:
                        reg_candidates.append((score, r))
                else:
                    if q_lower in name_val.lower():
                        reg_candidates.append((1.0, r))
                        if not cursor and len(reg_candidates) >= (offset or 0) + limit:
                            break
            
            if cursor:
                reg_candidates = [c for c in reg_candidates if c[1].get(reg_id_col) > cursor]
            if fuzzy:
                reg_candidates.sort(key=lambda x: x[0], reverse=True)
            start_idx = offset or 0
            results["regencies"] = [c[1] for c in reg_candidates[start_idx : start_idx + limit]]

        # 3. Search Districts
        dist_candidates = []
        for d in self.reader.read_districts():
            d_id = d.get(dist_id_col) or ""
            if scope_dist and d_id != scope_dist:
                continue
            if scope_reg and d.get(dist_reg_id_col) != scope_reg:
                continue
            if scope_prov and not d_id.startswith(scope_prov):
                continue
            name_val = d.get(dist_name_col)
            if not name_val:
                continue
            
            if fuzzy:
                if _should_prune(name_val):
                    continue
                score = string_similarity(query, name_val, method=similarity_method)
                if score >= threshold:
                    dist_candidates.append((score, d))
            else:
                if q_lower in name_val.lower():
                    dist_candidates.append((1.0, d))
                    if not cursor and len(dist_candidates) >= (offset or 0) + limit:
                        break
        
        if cursor:
            dist_candidates = [c for c in dist_candidates if c[1].get(dist_id_col) > cursor]
        if fuzzy:
            dist_candidates.sort(key=lambda x: x[0], reverse=True)
        start_idx = offset or 0
        results["districts"] = [c[1] for c in dist_candidates[start_idx : start_idx + limit]]

        # 4. Search Villages (Optimize read using partitions if scoped)
        if scope_dist:
            villages_source = self.reader.read_villages(district_id=scope_dist)
        elif scope_reg:
            villages_source = self.reader.read_villages(province_id=scope_reg[:2])
        elif scope_prov:
            villages_source = self.reader.read_villages(province_id=scope_prov)
        else:
            villages_source = self.reader.stream_all_villages()

        vil_candidates = []
        for v in villages_source:
            v_dist = v.get(vil_dist_id_col) or ""
            if scope_dist and v_dist != scope_dist:
                continue
            if scope_reg and not v_dist.startswith(scope_reg):
                continue
            if scope_prov and not v_dist.startswith(scope_prov):
                continue
            name_val = v.get(vil_name_col)
            if not name_val:
                continue
            
            if fuzzy:
                if _should_prune(name_val):
                    continue
                score = string_similarity(query, name_val, method=similarity_method)
                if score >= threshold:
                    vil_candidates.append((score, v))
            else:
                if q_lower in name_val.lower():
                    vil_candidates.append((1.0, v))
                    if not cursor and len(vil_candidates) >= (offset or 0) + limit:
                        break
        
        if cursor:
            vil_candidates = [c for c in vil_candidates if c[1].get(vil_id_col) > cursor]
        if fuzzy:
            vil_candidates.sort(key=lambda x: x[0], reverse=True)
        start_idx = offset or 0
        results["villages"] = [c[1] for c in vil_candidates[start_idx : start_idx + limit]]

        return results


