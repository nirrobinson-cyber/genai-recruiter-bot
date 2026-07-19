"""Embedding module package."""

__all__ = ["build_index"]


def __getattr__(name: str):
    if name == "build_index":
        from .build_index import build_index

        return build_index
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
