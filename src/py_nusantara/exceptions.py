class NusantaraError(Exception):
    """Base exception class for all py-nusantara exceptions."""
    pass


class ConfigurationError(NusantaraError):
    """Raised when there is an issue with the configuration (e.g. invalid columns, tables)."""
    pass


class IntegrityError(NusantaraError):
    """Raised when dataset integrity check fails (e.g. SHA-256 hash mismatch)."""
    pass


class DataNotFoundError(NusantaraError):
    """Raised when requested data or dataset files cannot be found."""
    pass


class NIKValidationError(NusantaraError):
    """Raised when NIK validation fails."""
    pass


class PostalCodeValidationError(NusantaraError):
    """Raised when Postal Code validation fails."""
    pass


