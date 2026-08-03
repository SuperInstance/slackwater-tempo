"""
slackwater_tempo — tempo is the first-class citizen.

Because in MIDI, the tempo is the first class citizen that everything else
depends on. As is life.

    >>> from slackwater_tempo import TempoMap, GrooveEngine, EnergyAdapter, BeatClock
    >>> clock = BeatClock()
    >>> tempo = TempoMap(bpm=72)
    >>> groove = GrooveEngine()
    >>> energy = EnergyAdapter(tempo)

Public API:
    TempoMap      — BPM tracking, smooth transitions, beat callbacks
    GrooveEngine  — swing, micro-timing, game-state presets
    EnergyAdapter — player-behavior → BPM mapping
    BeatClock     — shared synchronizing clock
"""

from slackwater_tempo.tempo import TempoMap, BeatCallback, TransitionCurve, TimeSignature
from slackwater_tempo.groove import GrooveEngine, TempoPreset, GameState
from slackwater_tempo.energy import EnergyAdapter, PlayerBehavior, ActivityLevel
from slackwater_tempo.clock import BeatClock

__version__ = "0.1.0"
__all__ = [
    "TempoMap",
    "BeatCallback",
    "TransitionCurve",
    "TimeSignature",
    "GrooveEngine",
    "TempoPreset",
    "GameState",
    "EnergyAdapter",
    "PlayerBehavior",
    "ActivityLevel",
    "BeatClock",
]
