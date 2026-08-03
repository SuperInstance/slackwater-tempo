"""
TempoMap — the heart of slackwater-tempo.

A tempo map is not a metronome marking. It is a *composed* record of how
the system's tempo character changes through its life and work. This module
implements BPM tracking with smooth transitions (accelerando / ritardando),
time-signature support, and beat-scheduling callbacks so that every agent
in the system can land on the same beat.

The key insight from Casey:

    "In MIDI, the tempo is the first class citizen that everything else
     depends on; as is life."

So we don't just store a number. We store the *character* of time.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional


# ── Transition curves ────────────────────────────────────────────────

class TransitionCurve(Enum):
    """How we get from one tempo to another.

    LINEAR is a metronome changing speed.
    EASE is a musician settling into the new tempo.
    SIGMOID is a band *feeling* the shift — slow start, fast middle,
    gentle landing. This is the default because it sounds the most human.
    """
    LINEAR = auto()
    EASE = auto()       # cosine ease-in-out
    SIGMOID = auto()    # smooth S-curve (logistic)


def _apply_curve(progress: float, curve: TransitionCurve) -> float:
    """Map linear 0→1 progress through a shaping curve, returning 0→1."""
    p = max(0.0, min(1.0, progress))
    if curve is TransitionCurve.LINEAR:
        return p
    if curve is TransitionCurve.EASE:
        # cosine ease-in-out — gentle on both ends
        return 0.5 * (1.0 - math.cos(math.pi * p))
    # sigmoid-ish via tanh
    # maps p through a smooth S-curve centred at 0.5
    return 0.5 + 0.5 * math.tanh(6.0 * (p - 0.5)) / math.tanh(3.0)


# ── Callback protocol ───────────────────────────────────────────────

@dataclass
class BeatCallback:
    """A scheduled callback registered with the TempoMap.

    on_beat         fires exactly on each beat (or every *period* beats).
    after_beat      fires *offset* seconds after each beat (for echoes,
                    reactions, the "and" of a beat).
    between_beats   fires *count* times evenly spaced between beats
                    (for subdivisions — 1 = eighth notes, 3 = sixteenths).

    All three are optional; set only what you need.
    """
    on_beat: Optional[Callable[[int, float], None]] = None
    after_beat: Optional[Callable[[int, float], None]] = None
    between_beats: Optional[Callable[[int, float], None]] = None
    # scheduling
    period: int = 1               # fire every *period* beats (1 = every beat)
    offset: float = 0.0           # seconds after the beat for after_beat
    subdivision_count: int = 0    # how many between-beat calls per beat
    # bookkeeping
    _last_fired_beat: int = field(default=-1, repr=False, compare=False)


# ── Time signature ───────────────────────────────────────────────────

@dataclass(frozen=True)
class TimeSignature:
    """A time signature: numerator / denominator.

    4/4 is the default. 3/4 is a waltz. 7/8 is for people who like
    to count.
    """
    numerator: int = 4
    denominator: int = 4

    def __post_init__(self):
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError("Time signature must be positive")
        # denominator must be a power of 2
        if self.denominator & (self.denominator - 1) != 0:
            raise ValueError(f"Denominator must be a power of 2, got {self.denominator}")

    @property
    def beats_per_bar(self) -> int:
        """How many beats in one bar."""
        return self.numerator

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


# ── The TempoMap itself ──────────────────────────────────────────────

class _ActiveTransition:
    """Internal: a smooth tempo change in progress."""

    __slots__ = ("start_bpm", "target_bpm", "start_time", "duration", "curve")

    def __init__(
        self,
        start_bpm: float,
        target_bpm: float,
        start_time: float,
        duration: float,
        curve: TransitionCurve,
    ):
        self.start_bpm = start_bpm
        self.target_bpm = target_bpm
        self.start_time = start_time
        self.duration = max(0.001, duration)  # avoid div-by-zero
        self.curve = curve

    def current_bpm(self, now: float) -> float:
        """Interpolated BPM at *now*."""
        elapsed = now - self.start_time
        if elapsed <= 0:
            return self.start_bpm
        if elapsed >= self.duration:
            return self.target_bpm
        progress = elapsed / self.duration
        shaped = _apply_curve(progress, self.curve)
        return self.start_bpm + (self.target_bpm - self.start_bpm) * shaped

    def is_done(self, now: float) -> bool:
        return (now - self.start_time) >= self.duration


class TempoMap:
    """The composed tempo of the system.

    A TempoMap tracks the current BPM and manages smooth transitions
    between tempos — accelerando (speeding up) and ritardando (slowing
    down). It schedules callbacks for on-beat, after-beat, and
    between-beat events.

    Usage::

        tempo = TempoMap(bpm=72)
        tempo.on_beat(lambda beat, t: print(f"beat {beat}"))
        tempo.set_bpm(120, transition_time=4.0)  # 4-second accelerando
        tempo.update(time.monotonic())            # call every frame

    The tempo map does NOT own a thread. The caller is responsible for
    pumping ``update()`` (typically from a game loop or audio callback).
    """

    def __init__(
        self,
        bpm: float = 120.0,
        time_signature: TimeSignature | None = None,
    ):
        if bpm <= 0:
            raise ValueError(f"BPM must be positive, got {bpm}")
        self._bpm: float = float(bpm)
        self._base_bpm: float = float(bpm)       # the anchor before a transition
        self._time_signature: TimeSignature = time_signature or TimeSignature()
        self._transition: Optional[_ActiveTransition] = None

        # Beat tracking
        self._beat: int = 0          # total beats since start
        self._bar: int = 0           # current bar number
        self._beat_in_bar: int = 0   # 0-indexed within the current bar
        self._last_beat_time: float = 0.0
        self._beat_accumulator: float = 0.0  # fractional beat progress

        # Registered callbacks
        self._callbacks: list[BeatCallback] = []

        # Subdivision tracking
        self._last_subdivision: int = -1

    # ── Properties ──────────────────────────────────

    @property
    def bpm(self) -> float:
        """Current instantaneous BPM (interpolated during transitions)."""
        if self._transition is not None:
            self._bpm = self._transition.current_bpm(time.monotonic())
        return self._bpm

    @property
    def base_bpm(self) -> float:
        """The target BPM (where we're heading or where we settled)."""
        return self._base_bpm

    @property
    def time_signature(self) -> TimeSignature:
        return self._time_signature

    @property
    def beat(self) -> int:
        """Total beat count since start."""
        return self._beat

    @property
    def bar(self) -> int:
        """Current bar number (0-indexed)."""
        return self._bar

    @property
    def beat_in_bar(self) -> int:
        """Beat within the current bar (0-indexed)."""
        return self._beat_in_bar

    @property
    def is_transitioning(self) -> bool:
        """True if a tempo transition is in progress."""
        return self._transition is not None and not self._transition.is_done(
            time.monotonic()
        )

    @property
    def seconds_per_beat(self) -> float:
        """Duration of one beat in seconds at the current BPM."""
        return 60.0 / self.bpm

    # ── Tempo control ──────────────────────────────

    def set_bpm(
        self,
        target: float,
        *,
        transition_time: float = 0.0,
        curve: TransitionCurve = TransitionCurve.SIGMOID,
    ) -> None:
        """Set a new target BPM.

        If *transition_time* > 0, the change is smooth (accelerando if
        speeding up, ritardando if slowing down). If 0, it is immediate.

        The curve defaults to SIGMOID because that is the shape of a
        musician settling into a new tempo — not a metronome snapping.
        """
        if target <= 0:
            raise ValueError(f"BPM must be positive, got {target}")
        now = time.monotonic()
        current = self.bpm  # sample current before replacing transition
        self._base_bpm = float(target)
        if transition_time > 0 and abs(target - current) > 0.01:
            self._transition = _ActiveTransition(
                start_bpm=current,
                target_bpm=float(target),
                start_time=now,
                duration=transition_time,
                curve=curve,
            )
        else:
            self._bpm = float(target)
            self._transition = None

    def accelerando(self, target: float, duration: float = 4.0) -> None:
        """Gradually speed up to *target* BPM over *duration* seconds."""
        if target < self.bpm:
            raise ValueError(
                f"Accelerando target ({target}) should be faster than current ({self.bpm})"
            )
        self.set_bpm(target, transition_time=duration)

    def ritardando(self, target: float, duration: float = 4.0) -> None:
        """Gradually slow down to *target* BPM over *duration* seconds."""
        if target > self.bpm:
            raise ValueError(
                f"Ritardando target ({target}) should be slower than current ({self.bpm})"
            )
        self.set_bpm(target, transition_time=duration)

    def set_time_signature(self, ts: TimeSignature) -> None:
        self._time_signature = ts

    # ── Callback registration ─────────────────────

    def add_callback(self, callback: BeatCallback) -> BeatCallback:
        """Register a BeatCallback. Returns it for chaining."""
        self._callbacks.append(callback)
        return callback

    def remove_callback(self, callback: BeatCallback) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def on_beat(
        self,
        fn: Callable[[int, float], None],
        *,
        period: int = 1,
    ) -> BeatCallback:
        """Convenience: register an on-beat callback.

        *fn* receives (beat_number, timestamp).
        *period*: fire every N beats (1 = every beat, 4 = once per bar in 4/4).
        """
        cb = BeatCallback(on_beat=fn, period=period)
        return self.add_callback(cb)

    def after_beat(
        self,
        fn: Callable[[int, float], None],
        *,
        offset: float = 0.05,
    ) -> BeatCallback:
        """Register an after-beat callback that fires *offset* seconds late."""
        cb = BeatCallback(after_beat=fn, offset=offset)
        return self.add_callback(cb)

    def between_beats(
        self,
        fn: Callable[[int, float], None],
        *,
        count: int = 1,
    ) -> BeatCallback:
        """Register a between-beat callback for subdivisions.

        *count* = 1 gives eighth-note spacing (one call between beats).
        *count* = 3 gives sixteenth-note spacing.
        """
        cb = BeatCallback(between_beats=fn, subdivision_count=count)
        return self.add_callback(cb)

    # ── Main update loop ───────────────────────────

    def update(self, now: float) -> None:
        """Advance the tempo map. Call this every frame.

        *now* should be a monotonic timestamp (e.g. time.monotonic()).
        """
        if self._last_beat_time == 0.0:
            # First update — initialise without firing callbacks
            self._last_beat_time = now
            return

        # Resolve any completed transition
        if self._transition is not None and self._transition.is_done(now):
            self._bpm = self._transition.target_bpm
            self._transition = None

        # Calculate elapsed time since last frame
        dt = now - self._last_beat_time
        if dt <= 0:
            return

        current_bpm = self.bpm
        spb = 60.0 / current_bpm  # seconds per beat

        # Accumulate fractional beats
        self._beat_accumulator += dt / spb

        # Fire whole beats
        while self._beat_accumulator >= 1.0:
            self._beat_accumulator -= 1.0
            self._beat += 1
            self._beat_in_bar += 1
            if self._beat_in_bar >= self._time_signature.beats_per_bar:
                self._beat_in_bar = 0
                self._bar += 1

            beat_time = now - self._beat_accumulator * spb

            # Fire on-beat callbacks
            for cb in self._callbacks:
                if cb.on_beat is not None:
                    if self._beat - cb._last_fired_beat >= cb.period or cb._last_fired_beat < 0:
                        cb.on_beat(self._beat, beat_time)
                        cb._last_fired_beat = self._beat

                # Fire after-beat callbacks (conceptually — in a real audio
                # engine these would be scheduled with sample accuracy; here
                # we fire them immediately for simplicity)
                if cb.after_beat is not None and cb.offset > 0:
                    # We pass the beat_time + offset as the "intended" fire time
                    cb.after_beat(self._beat, beat_time + cb.offset)

        # Fire between-beat subdivisions
        for cb in self._callbacks:
            if cb.between_beats is not None and cb.subdivision_count > 0:
                total_subs = cb.subdivision_count
                # Which subdivision are we on?
                current_sub = int(self._beat_accumulator * (total_subs + 1))
                if current_sub != self._last_subdivision and 0 < current_sub <= total_subs:
                    sub_time = now
                    cb.between_beats(self._beat, sub_time)
                    self._last_subdivision = current_sub
                elif current_sub == 0:
                    self._last_subdivision = -1

        self._last_beat_time = now

    # ── Utility ────────────────────────────────────

    def beat_phase(self) -> float:
        """Where we are in the current beat, 0.0 → 1.0.

        0.0 = just landed on the beat.
        0.5 = halfway to the next beat.
        1.0 = about to hit the next beat.
        """
        return self._beat_accumulator

    def __repr__(self) -> str:
        ts = self._time_signature
        status = "→" if self.is_transitioning else "@"
        return (
            f"TempoMap({status} {self.bpm:.1f} BPM, "
            f"{ts}, beat={self._beat}, bar={self._bar})"
        )
