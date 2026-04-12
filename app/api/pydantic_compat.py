"""Compatibility helpers for Pydantic v1/v2 model serialization."""

from typing import Any, Dict


def model_dump_compat(model: Any, **kwargs: Any) -> Dict[str, Any]:
    """Return a dict for either Pydantic v1 or v2 models."""
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)
