class OpenEMRError(RuntimeError):
    """Base class for OpenEMR integration errors."""


class OpenEMRConfigError(OpenEMRError):
    """Raised when mandatory OpenEMR settings are missing or invalid."""


class OpenEMRAuthError(OpenEMRError):
    """Raised when OpenEMR authentication fails."""


class OpenEMRRequestError(OpenEMRError):
    """Raised when the OpenEMR API request fails."""


class OpenEMRResponseError(OpenEMRError):
    """Raised when OpenEMR returns an unexpected response payload."""
