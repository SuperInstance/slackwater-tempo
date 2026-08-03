"""
BeatClock — the shared heartbeat.

All agents sync to this clock. It is the "tempo as first-class citizen"
made real: one source of truth for *when* now is, measured in beats
and bars, not seconds and milliseconds.

The BeatClock wraps a TempoMap and provides a simple API for agents
to query: ``current_beat()``, ``current_bar()``, ``bpm()``. It also
provides ``tick()`` for game loops that want to advance the clock
manually (useful for testing or deterministic replay).

In the unified framework, the BeatClock is the conductor's baton.
Every agent reads from it. Every groove aligns to it. The energy
adapter drives it. It is the one clock that rules them all.
"""

from __future__ import annotations

import time
from typing import Optional

from slackwater_tempo.tempo import TempoMap, TimeSignature, BeatCallback


class BeatClock:
    """The shared clock for all agents.

    A BeatClock owns a TempoMap and provides convenience methods.
    It is the single time source that every agent, groove, and
    callback should reference.

    Usage (manual tick — for game loops)::

        clock = BeatClock(bpm=72)
        while running:
            now = time.monotonic()
            clock.tick(now)

    Usage (query only — if update is handled elsewhere)::

        clock = BeatClock(bpm=72)
        if clock.current_beat() % 4 == 0:
            print("downbeat!")

    The clock does NOT own a thread. It is driven externally by
    the game loop or audio callback via ``tick()``.
    """

    def __init__(
        self,
        bpm: float = 120.0,
        time_signature: TimeSignature | None = None,
        tempo_map: Optional[TempoMap] = None,
    ):
        """Create a clock.

        You can pass an existing TempoMap, or let the clock create one
        from bpm and time_signature.
        """
        self._tempo: TempoMap = tempo_map or TempoMap(
            bpm=bpm, time_signature=time_signature
        )
        self._start_time: float = time.monotonic()
        self._last_tick: float = self._start_time
        self._is_running: bool = True

    # ── Properties (delegate to TempoMap) ──────────

    @property
    def tempo_map(self) -> TempoMap:
        """Direct access to the underlying TempoMap."""
        return self._tempo

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ── Query API ──────────────────────────────────

    def bpm(self) -> float:
        """Current instantaneous BPM."""
        return self._tempo.bpm

    def current_beat(self) -> int:
        """Total beats since the clock started."""
        return self._tempo.beat

    def current_bar(self) -> int:
        """Current bar number (0-indexed)."""
        return self._tempo.bar

    def beat_in_bar(self) -> int:
        """Beat within the current bar (0-indexed)."""
        return self._tempo.beat_in_bar

    def is_downbeat(self) -> bool:
        """True if the current beat is the first in the bar."""
        return self._tempo.beat_in_bar == 0

    def beat_phase(self) -> float:
        """Where in the current beat we are, 0.0 → 1.0."""
        return self._tempo.beat_phase()

    def elapsed_seconds(self) -> float:
        """Wall-clock seconds since the clock started."""
        return time.monotonic() - self._start_time

    def time_signature(self) -> TimeSignature:
        return self._tempo.time_signature

    def seconds_per_beat(self) -> float:
        return self._tempo.seconds_per_beat

    # ── Control ────────────────────────────────────

    def tick(self, now: Optional[float] = None) -> None:
        """Advance the clock one frame.

        Call this every frame from your game loop.
        If *now* is omitted, uses ``time.monotonic()``.
        """
        if not self._is_running:
            return
        if now is None:
            now = time.monotonic()
        self._tempo.update(now)
        self._last_tick = now

    def pause(self) -> None:
        """Pause the clock. ``tick()`` becomes a no-op."""
        self._is_running = False

    def resume(self) -> None:
        """Resume after pause. Resets the last-beat-time to avoid
        a huge jump."""
        self._is_running = True
        now = time.monotonic()
        self._tempo._last_beat_time = now
        self._last_tick = now

    def set_bpm(self, bpm: float, **kwargs) -> None:
        """Delegate to the TempoMap's ``set_bpm``."""
        self._tempo.set_bpm(bpm, **kwargs)

    def set_time_signature(self, ts: TimeSignature) -> None:
        self._tempo.set_time_signature(ts)

    # ── Callback registration (delegate) ───────────

    def on_beat(self, fn, **kwargs) -> BeatCallback:
        return self._tempo.on_beat(fn, **kwargs)

    def after_beat(self, fn, **kwargs) -> BeatCallback:
        return self._tempo.after_beat(fn, **kwargs)

    def between_beats(self, fn, **kwargs) -> BeatCallback:
        return self._tempo.between_beats(fn, **kwargs)

    def add_callback(self, cb: BeatCallback) -> BeatCallback:
        return self._tempo.add_callback(cb)

    # ── Sync helpers ───────────────────────────────

    def beats_away(self, target_beat: int) -> float:
        """How many beats until *target_beat*?

        Returns a positive float if target is in the future,
        negative if it's in the past.
        """
        return float(target_beat - self.current_beat())

    def next_downbeat(self) -> int:
        """The beat number of the next downbeat (start of next bar)."""
        beats_per_bar = self._tempo.time_signature.beats_per_bar
        current = self.current_beat()
        beats_into_bar = self._tempo.beat_in_bar
        if beats_into_bar == 0 and self.beat_phase() < 0.1:
            # We're basically on the downbeat right now
            return current
        return current + (beats_per_bar - beats_into_bar)

    def __repr__(self) -> str:
        ts = self._tempo.time_signature
        running = "▶" if self._is_running else "⏸"
        return (
            f"BeatClock({running} {self.bpm():.1f} BPM {ts}, "
            f"beat={self.current_beat()}, bar={self.current_bar()})"
        )
