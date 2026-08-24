"""Shared exception types for the zh Python package."""


class ZhApiError(RuntimeError):
    """Anything wrong with config, transport, or the GraphQL response."""
