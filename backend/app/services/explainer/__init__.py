"""Phase 7 explainer: template text from computed numbers only (no LLM)."""
from .drivers import TEMPLATES, describe, describe_all, driver_text
from .recommendation import explain, plain_text, sentences, with_sensitivity

__all__ = ["TEMPLATES", "describe", "describe_all", "driver_text", "explain", "plain_text", "sentences",
           "with_sensitivity"]
