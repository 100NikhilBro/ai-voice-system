"""
Q4 Live Insights / Nudges Pipeline
====================================
Provides real-time signal detection and nudge generation during calls.
"""
from .signal_detector import SignalDetector, Signal, SignalType
from .nudge_engine import NudgeEngine, Nudge, NudgePriority
from .latency_tracker import LatencyTracker, LatencyRecord
from .replay_engine import TranscriptReplayEngine

__all__ = [
    "SignalDetector", "Signal", "SignalType",
    "NudgeEngine", "Nudge", "NudgePriority",
    "LatencyTracker", "LatencyRecord",
    "TranscriptReplayEngine",
]
