"""
GrooveEngine — the feel of the beat.

A metronome marks equal divisions of time. A groove *shapes* those
divisions. Swing pushes the off-beats later. Push/drag nudges everything
slightly ahead of or behind the grid. The result is that two systems
with the same BPM can have wildly different feel — because groove is
not speed, it is *character*.

Game-state presets map tempo markings to situations:

    Adagio  — calm, exploratory, morning builds
    Andante — moderate, steady progress
    Allegro — active, engaged, under pressure
    Presto  — urgent, chaotic, storm repairs

These are not arbitrary numbers. They are musical tempo markings that
carry *character* — and that character should match the moment.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from slackwater_tempo.tempo import TempoMap, TransitionCurve


# ── Game state ↔ tempo preset ───────────────────────────────────────

class GameState(Enum):
    """High-level game states mapped to musical tempo markings."""
    CALM = auto()        # Adagio — morning, exploration, idle
    STEADY = auto()      # Andante — normal building, moderate engagement
    ACTIVE = auto()      # Allegro — active building, engaged, mild pressure
    URGENT = auto()      # Presto — storms, time pressure, chaotic events


@dataclass(frozen=True)
class TempoPreset:
    """A named tempo with its BPM range and character.

    The *character* string is the musical meaning — what it feels like
    in the game world. This is not decoration; it is the information
    that determines *why* this tempo was chosen.
    """
    name: str           # Italian marking: Adagio, Andante, Allegro, Presto
    bpm: float          # Target BPM
    character: str      # What this tempo *means* in context
    state: GameState

    def __str__(self) -> str:
        return f"{self.name} ({self.bpm:.0f} BPM) — {self.character}"


# ── The presets ─────────────────────────────────────────────────────

PRESETS: dict[GameState, TempoPreset] = {
    GameState.CALM: TempoPreset(
        name="Adagio",
        bpm=66.0,
        character="Slow, expressive, contemplative. Morning light on still water.",
        state=GameState.CALM,
    ),
    GameState.STEADY: TempoPreset(
        name="Andante",
        bpm=92.0,
        character="Walking pace, steady progress. The workhorse tempo.",
        state=GameState.STEADY,
    ),
    GameState.ACTIVE: TempoPreset(
        name="Allegro",
        bpm=132.0,
        character="Fast, lively, engaged. Building with intent.",
        state=GameState.ACTIVE,
    ),
    GameState.URGENT: TempoPreset(
        name="Presto",
        bpm=168.0,
        character="Very fast, urgent. Storm repair, time pressure, chaos.",
        state=GameState.URGENT,
    ),
}


# ── The GrooveEngine ────────────────────────────────────────────────

@dataclass
class GrooveEngine:
    """Shapes the raw beat into something with feel.

    GROOVE = SWING + MICRO-TIMING + TEMPO MAP

    **Swing** (0.0 = straight, 1.0 = full swing):
        In straight time, eighth notes are equal: |x x|x x|x x|
        In swing time, the off-beat is delayed:   |x-- x|x-- x|
        A swing of ~0.6 gives a classic jazz ride
        feel. 0.55 is a gentle lope. 0.0 is a march.

    **Push/Drag** (in milliseconds, ±10ms):
        Negative = push (ahead of the beat — eager, driving)
        Positive = drag (behind the beat — laid-back, heavy)
        Zero = dead on the grid (robotic)

    **Humanization**:
        Random ±variation added to each event's timing.
        Without this, even a swung groove sounds mechanical.
        With it, the groove breathes.

    Usage::

        groove = GrooveEngine(swing=0.6, drag_ms=3.0)
        offset = groove.timing_offset(beat_in_bar=1, is_off_beat=False)
        # offset is in seconds — add to the scheduled beat time
    """

    swing: float = 0.0
    """0.0 = straight, 1.0 = full swing. ~0.6 = classic jazz."""

    push_drag_ms: float = 0.0
    """Negative pushes ahead of the beat; positive drags behind."""

    humanize_ms: float = 0.0
    """Random timing variation per event, in milliseconds. 0 = off."""

    current_preset: Optional[TempoPreset] = None
    """The active tempo preset, if one has been set."""

    # Internal
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    # ── Groove settings ────────────────────────────

    def set_swing(self, swing: float) -> None:
        """Set swing factor. Clamped to [0.0, 1.0]."""
        self.swing = max(0.0, min(1.0, swing))

    def set_push_drag(self, ms: float) -> None:
        """Set push/drag in milliseconds. Clamped to ±10ms."""
        self.push_drag_ms = max(-10.0, min(10.0, ms))

    def set_humanize(self, ms: float) -> None:
        """Set humanization variation in milliseconds."""
        self.humanize_ms = max(0.0, ms)

    # ── Timing offset ──────────────────────────────

    def swing_offset(self, beat_in_bar: int) -> float:
        """How many seconds to delay a note based on swing.

        Off-beats (odd beats in a 2-beat grouping) get delayed.
        Downbeats stay on the grid.
        """
        if self.swing <= 0.0:
            return 0.0
        # In a typical swing, every other eighth is delayed.
        # beat_in_bar: 0=downbeat (on grid), 1=off-beat (delayed), etc.
        if beat_in_bar % 2 == 1:
            # Delay proportional to swing factor
            # Max delay at swing=1.0 is roughly 1/3 of the beat
            return self.swing * (1.0 / 3.0)
        return 0.0

    def timing_offset(
        self,
        beat_in_bar: int = 0,
        is_off_beat: bool = False,
    ) -> float:
        """Total timing offset in seconds for one event.

        Combines swing, push/drag, and humanization.
        Add this to the scheduled beat time to get the *felt* time.

        Parameters:
            beat_in_bar: position in the bar (for swing calculation)
            is_off_beat: if True, always apply swing (even on even beats
                         if the caller knows it's a subdivision)
        """
        offset = 0.0

        # Swing
        if is_off_beat or (beat_in_bar % 2 == 1):
            offset += self.swing * (1.0 / 3.0)

        # Push / drag (constant for this groove)
        offset += self.push_drag_ms / 1000.0

        # Humanization (random per call)
        if self.humanize_ms > 0.0:
            offset += self._rng.uniform(-self.humanize_ms, self.humanize_ms) / 1000.0

        return offset

    # ── Game state presets ─────────────────────────

    def apply_preset(
        self,
        state: GameState,
        tempo: TempoMap,
        *,
        transition_time: float = 4.0,
    ) -> TempoPreset:
        """Apply a game-state tempo preset to a TempoMap.

        Returns the preset that was applied.
        """
        preset = PRESETS[state]
        self.current_preset = preset
        tempo.set_bpm(preset.bpm, transition_time=transition_time)
        return preset

    def get_preset(self, state: GameState) -> TempoPreset:
        """Look up the preset for a game state without applying it."""
        return PRESETS[state]

    # ── Groove detection ───────────────────────────

    def is_in_the_pocket(self) -> bool:
        """Heuristic: are we in the pocket?

        "In the pocket" is when the groove feels right — the swing is
        present but not extreme, the push/drag is subtle, and the whole
        thing breathes. This is a rough heuristic, not a measurement of
        the harmony governor's Φ — but it captures the groove side.

        A groove is "in the pocket" when:
        - Swing is between 0.45 and 0.70 (human feel range)
        - Push/drag is within ±5ms (subtle, not sloppy)
        """
        swing_ok = 0.45 <= self.swing <= 0.70
        push_drag_ok = abs(self.push_drag_ms) <= 5.0
        return swing_ok and push_drag_ok

    # ── Presets for different agents ───────────────

    def agent_groove(self, agent_name: str) -> dict:
        """Return groove parameters suited to a specific agent.

        Different agents have different feels — Lucineer is deliberate
        and slightly behind the beat. Earl is eager and slightly ahead.
        The player is the reference (on the grid).
        """
        agent_grooves = {
            "lucineer": {
                "swing": 0.55,
                "push_drag_ms": 4.0,   # behind the beat — laid-back, heavy
                "humanize_ms": 2.0,
                "character": "Deliberate, weighty. The hammer falls slightly late.",
            },
            "earl": {
                "swing": 0.50,
                "push_drag_ms": -3.0,  # ahead of the beat — eager, quick
                "humanize_ms": 1.5,
                "character": "Eager, quick. Always ready before you ask.",
            },
            "player": {
                "swing": 0.0,           # the player sets the grid
                "push_drag_ms": 0.0,
                "humanize_ms": 0.0,
                "character": "The reference. Everything aligns to the player.",
            },
        }
        return agent_grooves.get(agent_name, agent_grooves["player"])

    def apply_agent_groove(self, agent_name: str) -> None:
        """Apply an agent's characteristic groove to this engine."""
        groove = self.agent_groove(agent_name)
        self.set_swing(groove["swing"])
        self.set_push_drag(groove["push_drag_ms"])
        self.set_humanize(groove["humanize_ms"])

    def __repr__(self) -> str:
        preset_name = self.current_preset.name if self.current_preset else "none"
        pocket = "★ in the pocket" if self.is_in_the_pocket() else ""
        return (
            f"GrooveEngine(swing={self.swing:.2f}, "
            f"push_drag={self.push_drag_ms:+.1f}ms, "
            f"humanize={self.humanize_ms:.1f}ms, "
            f"preset={preset_name}) {pocket}"
        )
