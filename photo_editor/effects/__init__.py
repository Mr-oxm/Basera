"""Runtime effects pipeline built on the shared image-processor contract.

Effects stay separate from adjustment/filter layers because they model an
ordered enable/disable post-process chain rather than document-owned layer
processors.
"""

from .effect_base import Effect
from .effects_pipeline import EffectsPipeline

__all__ = ["Effect", "EffectsPipeline"]
