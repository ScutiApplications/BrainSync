"""Shared error base. Messages are safe to show to the user: they never contain paths."""


class BrainSyncError(Exception):
    """An expected failure with a user-safe message."""
