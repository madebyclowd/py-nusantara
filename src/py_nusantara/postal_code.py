from typing import Any, Dict, List, Optional
from py_nusantara.exceptions import PostalCodeValidationError
from py_nusantara.records import VillageRecord


class PostalCodeInfo:
    """Represents the parsed information and resolved administrative regions for a postal code."""

    def __init__(
        self,
        postal_code: str,
        villages: List[Any],
        districts: List[Any],
        regencies: List[Any],
        provinces: List[Any],
    ):
        self.postal_code = postal_code
        self.villages = villages
        self.districts = districts
        self.regencies = regencies
        self.provinces = provinces

    def to_dict(self, logical: bool = True) -> Dict[str, Any]:
        """Convert the parsed postal code info and its resolved entities to a dictionary."""
        return {
            "postal_code": self.postal_code,
            "villages": [v.to_dict(logical) for v in self.villages],
            "districts": [d.to_dict(logical) for d in self.districts],
            "regencies": [r.to_dict(logical) for r in self.regencies],
            "provinces": [p.to_dict(logical) for p in self.provinces],
        }

    def __repr__(self) -> str:
        return (
            f"<PostalCodeInfo postal_code={self.postal_code} "
            f"villages={len(self.villages)} districts={len(self.districts)}>"
        )


def validate_postal_code(postal_code: str) -> bool:
    """Validate if the given postal code is a syntactically valid Indonesian postal code.
    
    Indonesian postal codes are exactly 5 digits, numeric, and do not start with '0'.
    """
    if not isinstance(postal_code, str):
        return False
    
    code = postal_code.strip()
    if len(code) != 5:
        return False
    
    if not code.isdigit():
        return False
        
    if code[0] == "0":
        return False
        
    return True


def parse_postal_code(postal_code: str, facade_ref: Optional[Any] = None) -> PostalCodeInfo:
    """Parse the postal code and resolve its administrative region hierarchy.
    
    Raises PostalCodeValidationError if the postal code is invalid.
    """
    if not isinstance(postal_code, str):
        raise PostalCodeValidationError("Postal code must be a string.")

    code = postal_code.strip()
    if not validate_postal_code(code):
        raise PostalCodeValidationError(
            f"Invalid postal code format: '{postal_code}'. "
            "Must be exactly 5 numeric digits and cannot start with '0'."
        )

    villages = []
    districts = []
    regencies = []
    provinces = []

    if facade_ref:
        # Load and filter matching villages
        # Using resolving helper in reader to stream villages
        postal_code_col = facade_ref.config.resolve_column_name("villages", "postal_code")
        
        matching_raw_villages = []
        for v_raw in facade_ref.reader.stream_all_villages():
            if v_raw.get(postal_code_col) == code:
                matching_raw_villages.append(v_raw)

        # Map to VillageRecord wrappers
        villages = [
            VillageRecord(v_raw, facade_ref.config, facade_ref)
            for v_raw in matching_raw_villages
        ]

        # Resolve distinct parents
        seen_districts = set()
        seen_regencies = set()
        seen_provinces = set()

        for v in villages:
            d = v.district
            if d and d.id not in seen_districts:
                seen_districts.add(d.id)
                districts.append(d)

                r = d.regency
                if r and r.id not in seen_regencies:
                    seen_regencies.add(r.id)
                    regencies.append(r)

                    p = r.province
                    if p and p.id not in seen_provinces:
                        seen_provinces.add(p.id)
                        provinces.append(p)

    return PostalCodeInfo(
        postal_code=code,
        villages=villages,
        districts=districts,
        regencies=regencies,
        provinces=provinces,
    )
