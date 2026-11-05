"""human-pace: decide when to reply based on how the user actually types."""

from .modes import kmeans1d, nearest, percentile
from .pace import Decision, Pace, PaceConfig
from .signals import Signal, read_signal
from .store import MemoryStore, ObservedStore, SqliteStore, Store

__version__ = "0.1.0"

__all__ = [
    "Pace",
    "PaceConfig",
    "Decision",
    "Signal",
    "read_signal",
    "kmeans1d",
    "nearest",
    "percentile",
    "MemoryStore",
    "SqliteStore",
    "ObservedStore",
    "Store",
    "__version__",
]
