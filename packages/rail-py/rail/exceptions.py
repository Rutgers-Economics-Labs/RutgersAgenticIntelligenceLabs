class RailError(Exception):
    """Base exception for all RAIL-related errors."""
    pass

class AuthError(RailError):
    """Raised when there is an authentication error with the platform API."""
    pass

class HydrationError(RailError):
    """Raised when a hydration pipeline fails."""
    pass