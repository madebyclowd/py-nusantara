def clean_region_code(code: str) -> str:
    """Cleans a regional code by removing dots and whitespace.
    
    Example: "32.73.01.2001" -> "3273012001"
    """
    if not isinstance(code, str):
        raise TypeError("Region code must be a string.")
    return code.replace(".", "").strip()


def format_region_code(code: str) -> str:
    """Formats a numeric regional code to BPS/Kepmendagri dot-separated format.
    
    Example: "3273012001" -> "32.73.01.2001"
    """
    if not isinstance(code, str):
        raise TypeError("Region code must be a string.")
    
    clean_code = clean_region_code(code)
    if not clean_code.isdigit():
        raise ValueError("Region code must contain only numeric digits.")

    length = len(clean_code)
    if length == 2:
        return clean_code
    elif length == 4:
        return f"{clean_code[0:2]}.{clean_code[2:4]}"
    elif length == 6:
        return f"{clean_code[0:2]}.{clean_code[2:4]}.{clean_code[4:6]}"
    elif length == 10:
        return f"{clean_code[0:2]}.{clean_code[2:4]}.{clean_code[4:6]}.{clean_code[6:10]}"
    else:
        raise ValueError(
            f"Invalid region code length: {length}. "
            "Must be 2 (Province), 4 (Regency), 6 (District), or 10 (Village) digits."
        )


def validate_region_code(code: str) -> bool:
    """Validates if a regional code conforms to Indonesia BPS/Kepmendagri length and numeric standard."""
    try:
        clean_code = clean_region_code(code)
        if not clean_code.isdigit():
            return False
        return len(clean_code) in (2, 4, 6, 10)
    except (TypeError, ValueError):
        return False
