"""
EnergyAdapter — the bridge between life and tempo.

Player behaviour IS energy. How fast they build, how long they idle,
how much they talk — these are signals. The EnergyAdapter reads those
signals and maps them to BPM. Low energy = Adagio. High energy =
Allegro. The transition is smooth — never a jump, because a jump
would be the system imposing its tempo on the human rather than
following theirs.

This is the Rubato principle from the tempo map essay: the system
follows the human's tempo, not the system's.

    "An interactive system that waits for the human is not slow.
     It is Rubato. The system should follow the human's tempo, not
     impose its own."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from slackwater_tempo.tempo import TempoMap, TransitionCurve


# ── Player behaviour ─────────────────────────────────────────────────

class ActivityLevel(Enum):
    """Discrete activity levels mapped to BPM ranges.

    These are not arbitrary — they correspond to musical dynamics:
    pp (pianissimo) through ff (fortissimo). The quieter levels are
    Adagio. The louder levels are Allegro. The system breathes with
    the player.
    """
    IDLE = auto()         # pp — no input for a while, player is looking around
    RELAXED = auto()      # p  — slow building, browsing, light interaction
    MODERATE = auto()     # mp — steady building, normal engagement
    ENGAGED = auto()      # mf — active building, frequent actions
    INTENSE = auto()      # f  — rapid building, high-frequency actions
    FRANTIC = auto()      # ff — very rapid, possibly stressed or rushing


@dataclass
class PlayerBehavior:
    """A snapshot of what the player is doing.

    All rates are per-minute. The EnergyAdapter smooths these into
    a single energy value and maps it to BPM.

    These fields are set by the game's telemetry — whatever system
    is watching the player sends updates here.
    """
    build_rate: float = 0.0      # blocks placed per minute
    idle_time: float = 0.0       # seconds since last meaningful action
    chat_frequency: float = 0.0  # messages per minute
    movement_speed: float = 0.0  # units per second (if applicable)
    action_rate: float = 0.0     # any meaningful actions per minute (doors, UI, etc.)

    def activity_level(self) -> ActivityLevel:
        """Classify the current behaviour into a discrete level.

        This is a heuristic — the thresholds are tuned for a building/
        creative game context. Adjust as needed.
        """
        # Idle: nothing happening
        if self.idle_time > 15.0 and self.build_rate < 1.0 and self.action_rate < 2.0:
            return ActivityLevel.IDLE

        total_activity = self.build_rate + self.action_rate + self.chat_frequency * 2

        if total_activity < 5:
            return ActivityLevel.RELAXED
        if total_activity < 20:
            return ActivityLevel.MODERATE
        if total_activity < 60:
            return ActivityLevel.ENGAGED
        if total_activity < 120:
            return ActivityLevel.INTENSE
        return ActivityLevel.FRANTIC

    @property
    def energy(self) -> float:
        """A continuous energy score from 0.0 (asleep) to 1.0 (maxed).

        This is the raw fuel for the BPM mapping. It combines all
        signals into a single number. The formula is intentionally
        simple — the smoothing is what makes it feel natural.
        """
        # Normalize each signal
        build_norm = min(1.0, self.build_rate / 120.0)        # 120/min = max
        chat_norm = min(1.0, self.chat_frequency / 30.0)      # 30/min = max
        action_norm = min(1.0, self.action_rate / 60.0)       # 60/min = max
        move_norm = min(1.0, self.movement_speed / 50.0)      # 50 u/s = max

        # Idle time reduces energy (after 5s of idle, energy starts dropping)
        idle_penalty = min(1.0, max(0.0, self.idle_time - 5.0) / 30.0)

        # Weighted combination — build rate dominates in a building game
        raw = (
            build_norm * 0.45
            + action_norm * 0.25
            + chat_norm * 0.15
            + move_norm * 0.15
        )

        return max(0.0, raw - idle_penalty * 0.5)


# ── Activity → BPM mapping ───────────────────────────────────────────

# Each activity level maps to a BPM target.
# These correspond to the GrooveEngine presets so the whole system
# stays coherent.
ACTIVITY_BPM: dict[ActivityLevel, float] = {
    ActivityLevel.IDLE: 60.0,      # Largo — nearly still, but alive
    ActivityLevel.RELAXED: 72.0,   # Adagio
    ActivityLevel.MODERATE: 92.0,  # Andante
    ActivityLevel.ENGAGED: 120.0,  # Moderato-Allegro
    ActivityLevel.INTENSE: 144.0,  # Allegro
    ActivityLevel.FRANTIC: 172.0,  # Presto
}


# ── The EnergyAdapter ───────────────────────────────────────────────

@dataclass
class EnergyAdapter:
    """Observes player behaviour and maps it to BPM.

    The adapter maintains a *smoothed* energy value that transitions
    gradually — never jumping. The smoothing time is configurable
    (default 7 seconds, in the 5-10 second range Casey specified).

    Usage::

        tempo = TempoMap(bpm=72)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=30, chat_frequency=5))
        adapter.update(time.monotonic())  # call every frame
        # tempo.bpm gradually shifts to match the player's energy

    Key design: the adapter NEVER sets BPM directly. It computes a
    target BPM from the player's energy and calls ``tempo.set_bpm()``
    with a transition time. The TempoMap handles the actual smooth
    interpolation. The adapter's job is to decide *what* tempo we're
    heading toward and *when* to change it.
    """

    tempo: TempoMap
    """The TempoMap to drive."""

    smoothing_seconds: float = 7.0
    """How long the BPM transition takes (5-10 recommended)."""

    min_bpm: float = 50.0
    """Floor BPM — the system never gets slower than this."""

    max_bpm: float = 180.0
    """Ceiling BPM — the system never gets faster than this."""

    # Internal state
    _current_energy: float = 0.0
    _target_energy: float = 0.0
    _last_behavior: Optional[PlayerBehavior] = None
    _last_update: float = 0.0
    _last_bpm_change: float = 0.0

    # Minimum seconds between BPM changes to prevent jitter
    _min_change_interval: float = 2.0

    # ── Observation ────────────────────────────────

    def observe(self, behavior: PlayerBehavior) -> None:
        """Receive a behaviour snapshot from the game.

        Call this whenever new telemetry arrives (e.g. once per second).
        The adapter computes the target energy and lets ``update()``
        handle the transition.
        """
        self._last_behavior = behavior
        self._target_energy = behavior.energy

    @property
    def current_energy(self) -> float:
        """The smoothed energy value (0.0 → 1.0)."""
        return self._current_energy

    @property
    def target_energy(self) -> float:
        """The energy we're transitioning toward."""
        return self._target_energy

    @property
    def activity_level(self) -> Optional[ActivityLevel]:
        """The player's current activity classification."""
        if self._last_behavior is None:
            return None
        return self._last_behavior.activity_level()

    # ── Energy → BPM ───────────────────────────────

    def energy_to_bpm(self, energy: float) -> float:
        """Map energy [0.0, 1.0] to BPM [min_bpm, max_bpm].

        Uses a slight exponential curve so low energy feels *calm*
        (not just "slow") and high energy feels *driven* (not just
        "fast"). The curve is:

            bpm = min + (max - min) * energy^0.8

        The 0.8 exponent makes the BPM rise a bit faster at low
        energy (so the system feels responsive) and a bit slower
        at high energy (so it doesn't max out too easily).
        """
        e = max(0.0, min(1.0, energy))
        normalized = e ** 0.8
        return self.min_bpm + (self.max_bpm - self.min_bpm) * normalized

    # ── Main update ────────────────────────────────

    def update(self, now: float) -> None:
        """Advance the energy adapter. Call every frame.

        Smooths the energy value and, when it has changed enough,
        tells the TempoMap to head toward a new BPM.
        """
        if self._last_update == 0.0:
            self._last_update = now
            self._current_energy = self._target_energy
            return

        dt = now - self._last_update
        if dt <= 0:
            return

        # Smoothly interpolate current energy toward target
        # Time constant: smoothing_seconds
        # Using exponential moving average with alpha = dt / (dt + tau)
        alpha = dt / (dt + self.smoothing_seconds)
        self._current_energy += (self._target_energy - self._current_energy) * alpha

        # Check if we should issue a BPM change
        if now - self._last_bpm_change < self._min_change_interval:
            self._last_update = now
            return

        # Compute target BPM from current energy
        target_bpm = self.energy_to_bpm(self._current_energy)
        current_bpm = self.tempo.bpm

        # Only issue a change if the difference is meaningful (> 3 BPM)
        if abs(target_bpm - current_bpm) > 3.0:
            self.tempo.set_bpm(
                target_bpm,
                transition_time=self.smoothing_seconds,
                curve=TransitionCurve.SIGMOID,
            )
            self._last_bpm_change = now

        self._last_update = now

    def __repr__(self) -> str:
        activity = self.activity_level
        activity_name = activity.name if activity else "unknown"
        return (
            f"EnergyAdapter(energy={self._current_energy:.2f} → {self._target_energy:.2f}, "
            f"activity={activity_name}, "
            f"target_bpm={self.energy_to_bpm(self._current_energy):.0f})"
        )
