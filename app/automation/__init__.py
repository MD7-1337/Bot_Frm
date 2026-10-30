"""Process-isolated automation proofs of concept.

Workers run trusted Python with the current user's permissions. They are not a
security sandbox. Device isolation applies to the provided API only.
"""

from .runtime import DeviceBusyError, RuntimeCoordinator, TrustRequiredError

__all__ = ["DeviceBusyError", "RuntimeCoordinator", "TrustRequiredError"]
