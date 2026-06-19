import datetime
from typing import Any, Dict, Optional, Tuple
from py_nusantara.exceptions import NIKValidationError


class NIKInfo:
    """Represents the parsed information from a NIK (Nomor Induk Kependudukan)."""

    def __init__(
        self,
        nik: str,
        province_id: str,
        regency_id: str,
        district_id: str,
        gender: str,
        birth_date: datetime.date,
        sequence: str,
        facade_ref: Optional[Any] = None,
    ):
        self.nik = nik
        self.province_id = province_id
        self.regency_id = regency_id
        self.district_id = district_id
        self.gender = gender
        self.birth_date = birth_date
        self.sequence = sequence
        self._facade = facade_ref

    @property
    def province(self) -> Optional[Any]:
        """Retrieve the ProvinceRecord matching this NIK's province code, if facade is available."""
        if not self._facade:
            return None
        return self._facade.find_province(self.province_id)

    @property
    def regency(self) -> Optional[Any]:
        """Retrieve the RegencyRecord matching this NIK's regency code, if facade is available."""
        if not self._facade:
            return None
        return self._facade.find_regency(self.regency_id)

    @property
    def district(self) -> Optional[Any]:
        """Retrieve the DistrictRecord matching this NIK's district code, if facade is available."""
        if not self._facade:
            return None
        return self._facade.find_district(self.district_id)

    def to_dict(self) -> Dict[str, Any]:
        """Return the parsed NIK information as a dictionary."""
        return {
            "nik": self.nik,
            "province_id": self.province_id,
            "regency_id": self.regency_id,
            "district_id": self.district_id,
            "gender": self.gender,
            "birth_date": self.birth_date,
            "sequence": self.sequence,
        }

    def __repr__(self) -> str:
        return (
            f"<NIKInfo nik={self.nik} gender={self.gender} "
            f"birth_date={self.birth_date} district_id={self.district_id}>"
        )


def _parse_nik_parts(
    nik: str, reference_year: Optional[int] = None
) -> Tuple[str, str, str, str, datetime.date, str]:
    """Helper function to validate NIK structure and parse component values.
    
    Raises NIKValidationError if NIK is invalid.
    """
    if not isinstance(nik, str):
        raise NIKValidationError("NIK must be a string.")

    nik = nik.strip()
    if len(nik) != 16:
        raise NIKValidationError("NIK must be exactly 16 characters long.")

    if not nik.isdigit():
        raise NIKValidationError("NIK must contain only numeric digits.")

    # Parse regional codes
    prov_code = nik[0:2]
    reg_code = nik[2:4]
    dist_code = nik[4:6]

    if prov_code == "00":
        raise NIKValidationError("Invalid NIK: Province code cannot be '00'.")
    if reg_code == "00":
        raise NIKValidationError("Invalid NIK: Regency code cannot be '00'.")
    if dist_code == "00":
        raise NIKValidationError("Invalid NIK: District code cannot be '00'.")

    province_id = prov_code
    regency_id = prov_code + reg_code
    district_id = prov_code + reg_code + dist_code

    # Parse gender and birth day
    day_part = int(nik[6:8])
    if 1 <= day_part <= 31:
        gender = "male"
        day = day_part
    elif 41 <= day_part <= 71:
        gender = "female"
        day = day_part - 40
    else:
        raise NIKValidationError(f"Invalid NIK: Day part '{nik[6:8]}' is invalid.")

    # Parse month
    month = int(nik[8:10])
    if not (1 <= month <= 12):
        raise NIKValidationError(f"Invalid NIK: Month part '{nik[8:10]}' is invalid.")

    # Parse year
    yy_part = int(nik[10:12])

    # Apply century threshold heuristic using the reference or current year
    current_year = reference_year or datetime.date.today().year
    year = 2000 + yy_part
    if year > current_year:
        year = 1900 + yy_part

    # Validate that it's a valid calendar date
    try:
        birth_date = datetime.date(year, month, day)
    except ValueError as e:
        raise NIKValidationError(
            f"Invalid NIK: Birth date {year}-{month:02d}-{day:02d} is invalid ({e})."
        )

    # Parse sequence number
    sequence = nik[12:16]
    if sequence == "0000":
        raise NIKValidationError("Invalid NIK: Sequence number cannot be '0000'.")

    return province_id, regency_id, district_id, gender, birth_date, sequence


def validate_nik(nik: str, reference_year: Optional[int] = None) -> bool:
    """Validate if the given NIK is syntactically valid."""
    try:
        _parse_nik_parts(nik, reference_year)
        return True
    except NIKValidationError:
        return False


def parse_nik(
    nik: str, reference_year: Optional[int] = None, facade_ref: Optional[Any] = None
) -> NIKInfo:
    """Parse the given NIK and return a NIKInfo object.
    
    Raises NIKValidationError if NIK is invalid.
    """
    province_id, regency_id, district_id, gender, birth_date, sequence = _parse_nik_parts(
        nik, reference_year
    )
    return NIKInfo(
        nik=nik,
        province_id=province_id,
        regency_id=regency_id,
        district_id=district_id,
        gender=gender,
        birth_date=birth_date,
        sequence=sequence,
        facade_ref=facade_ref,
    )
