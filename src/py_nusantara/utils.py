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


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def trigram_similarity(s1: str, s2: str) -> float:
    """Calculate the trigram Jaccard similarity between two strings."""
    s1_lower = s1.lower()
    s2_lower = s2.lower()
    if s1_lower == s2_lower:
        return 1.0
    if len(s1_lower) < 3 or len(s2_lower) < 3:
        # Fallback to normalized edit distance
        dist = levenshtein_distance(s1_lower, s2_lower)
        max_len = max(len(s1_lower), len(s2_lower), 1)
        return 1.0 - (dist / max_len)

    t1 = {s1_lower[i:i+3] for i in range(len(s1_lower) - 2)}
    t2 = {s2_lower[i:i+3] for i in range(len(s2_lower) - 2)}
    intersection = t1.intersection(t2)
    union = t1.union(t2)
    if not union:
        return 0.0
    return len(intersection) / len(union)


def string_similarity(s1: str, s2: str, method: str = "levenshtein") -> float:
    """Calculate similarity between two strings [0.0 - 1.0] using the specified method."""
    if not s1 or not s2:
        return 0.0
    s1_lower = s1.strip().lower()
    s2_lower = s2.strip().lower()
    
    if s1_lower == s2_lower:
        return 1.0

    # Helper to calculate similarity of two raw strings
    def _raw_sim(a: str, b: str) -> float:
        if method == "trigram":
            return trigram_similarity(a, b)
        dist = levenshtein_distance(a, b)
        max_len = max(len(a), len(b), 1)
        return 1.0 - (dist / max_len)

    # 1. Compare raw strings
    best_score = _raw_sim(s1_lower, s2_lower)

    # 2. Compare prefix-stripped strings
    def _strip_prefix(s: str) -> str:
        for prefix in ("kabupaten ", "kota ", "kecamatan ", "kelurahan ", "desa ", "provinsi ", "daerah istimewa "):
            if s.startswith(prefix):
                return s[len(prefix):].strip()
        return s

    s1_stripped = _strip_prefix(s1_lower)
    s2_stripped = _strip_prefix(s2_lower)
    if s1_stripped != s1_lower or s2_stripped != s2_lower:
        best_score = max(best_score, _raw_sim(s1_stripped, s2_stripped))

    # 3. Compare word-by-word to support partial word matches (e.g. "Jogjakarta" matching "Daerah Istimewa Yogyakarta")
    words2 = s2_stripped.split()
    if len(words2) > 1:
        for w in words2:
            best_score = max(best_score, _raw_sim(s1_stripped, w))
            
    return best_score


