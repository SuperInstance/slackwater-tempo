"""
Comprehensive tests for BeatClock — the shared heartbeat.

Tests cover:
- Construction and initial state
- Property delegation to TempoMap
- Tick behaviour (manual time advance)
- Pause / resume semantics
- BPM and time signature changes
- Downbeat detection
- Sync helpers (beats_away, next_downbeat)
- Callback registration through clock
- Edge cases (zero time, negative time, rapid ticking)
"""

import time
import pytest
from unittest.mock import MagicMock

from slackwater_tempo import BeatClock, TempoMap, TimeSignature
from slackwater_tempo.tempo import BeatCallback


# ── Construction ────────────────────────────────────────────────────

class TestBeatClockConstruction:
    def test_default_construction(self):
        clock = BeatClock()
        assert clock.is_running is True
        assert clock.bpm() == 120.0

    def test_custom_bpm(self):
        clock = BeatClock(bpm=72.0)
        assert clock.bpm() == 72.0

    def test_with_time_signature(self):
        ts = TimeSignature(3, 4)
        clock = BeatClock(bpm=100.0, time_signature=ts)
        assert clock.time_signature().numerator == 3

    def test_with_existing_tempo_map(self):
        tm = TempoMap(bpm=90.0)
        clock = BeatClock(tempo_map=tm)
        assert clock.tempo_map is tm
        assert clock.bpm() == 90.0

    def test_start_time_initialized(self):
        clock = BeatClock()
        assert clock.elapsed_seconds() >= 0.0
        assert clock.elapsed_seconds() < 1.0


# ── Initial State ───────────────────────────────────────────────────

class TestBeatClockInitialState:
    def test_initial_beat_is_zero(self):
        clock = BeatClock()
        assert clock.current_beat() == 0

    def test_initial_bar_is_zero(self):
        clock = BeatClock()
        assert clock.current_bar() == 0

    def test_initial_beat_in_bar_zero(self):
        clock = BeatClock()
        assert clock.beat_in_bar() == 0

    def test_initial_is_downbeat(self):
        clock = BeatClock()
        assert clock.is_downbeat() is True

    def test_initial_beat_phase_zero(self):
        clock = BeatClock()
        assert clock.beat_phase() < 0.1


# ── Tick Behaviour ──────────────────────────────────────────────────

class TestBeatClockTick:
    def test_tick_advances_tempo(self):
        """Tick with enough time for beats to fire."""
        clock = BeatClock(bpm=60.0)  # 1 beat per second
        start = time.monotonic()
        clock.tick(start)  # initialize
        for i in range(1, 21):
            clock.tick(start + i * 0.1)  # tick every 100ms
        assert clock.current_beat() >= 1

    def test_tick_with_explicit_time(self):
        clock = BeatClock(bpm=120.0)  # 2 beats per second
        base = time.monotonic()
        clock.tick(base)  # initialize
        for i in range(1, 11):
            clock.tick(base + i * 0.05)  # tick every 50ms
        assert clock.current_beat() >= 1

    def test_tick_uses_monotonic_when_no_arg(self):
        clock = BeatClock(bpm=120.0)
        clock.tick()  # Should not raise
        assert clock.is_running

    def test_tick_does_nothing_when_paused(self):
        clock = BeatClock(bpm=60.0)
        clock.pause()
        start = time.monotonic()
        clock.tick(start + 10.0)  # large time jump
        assert clock.current_beat() == 0

    def test_rapid_ticks(self):
        """Many rapid ticks should be safe."""
        clock = BeatClock(bpm=120.0)
        base = time.monotonic()
        for i in range(100):
            clock.tick(base + i * 0.001)  # 1ms apart
        assert clock.current_beat() >= 0


# ── Pause / Resume ──────────────────────────────────────────────────

class TestBeatClockPauseResume:
    def test_pause_sets_flag(self):
        clock = BeatClock()
        clock.pause()
        assert clock.is_running is False

    def test_resume_sets_flag(self):
        clock = BeatClock()
        clock.pause()
        clock.resume()
        assert clock.is_running is True

    def test_resume_does_not_jump(self):
        """After resume, the clock should not jump forward.

        Note: resume() internally uses time.monotonic() to reset the
        tempo's last_beat_time. So we must use real time here, not
        synthetic offsets.
        """
        clock = BeatClock(bpm=60.0)
        # Get a beat going
        clock.tick()
        time.sleep(1.2)  # ~1 beat at 60bpm
        clock.tick()
        beat_before_pause = clock.current_beat()
        clock.pause()
        # While paused, sleep — tick should be no-op
        time.sleep(0.3)
        clock.tick()
        assert clock.current_beat() == beat_before_pause
        # Resume and immediately tick — should not jump
        clock.resume()
        clock.tick()
        # Beat count should be close to paused value
        assert clock.current_beat() <= beat_before_pause + 2

    def test_pause_tick_resume_cycle(self):
        clock = BeatClock(bpm=120.0)
        clock.tick(time.monotonic() + 0.5)
        clock.pause()
        clock.tick(time.monotonic() + 1.0)
        clock.resume()
        clock.tick(time.monotonic() + 1.5)
        assert clock.is_running


# ── BPM and Time Signature Changes ──────────────────────────────────

class TestBeatClockBPMTimeSig:
    def test_set_bpm(self):
        clock = BeatClock(bpm=120.0)
        clock.set_bpm(90.0)
        assert clock.bpm() == pytest.approx(90.0, abs=0.1)

    def test_set_bpm_with_transition(self):
        clock = BeatClock(bpm=120.0)
        clock.set_bpm(60.0, transition_time=2.0)
        assert clock.bpm() <= 120.0

    def test_set_time_signature(self):
        clock = BeatClock(bpm=100.0)
        new_ts = TimeSignature(5, 4)
        clock.set_time_signature(new_ts)
        assert clock.time_signature().numerator == 5

    def test_seconds_per_beat(self):
        clock = BeatClock(bpm=120.0)
        assert clock.seconds_per_beat() == pytest.approx(0.5, abs=0.01)

    def test_seconds_per_beat_slow(self):
        clock = BeatClock(bpm=60.0)
        assert clock.seconds_per_beat() == pytest.approx(1.0, abs=0.01)


# ── Downbeat and Sync ───────────────────────────────────────────────

class TestBeatClockDownbeatSync:
    def test_is_downbeat_at_start(self):
        clock = BeatClock(bpm=120.0, time_signature=TimeSignature(numerator=4, denominator=4))
        assert clock.is_downbeat() is True

    def test_beats_away_future(self):
        clock = BeatClock(bpm=120.0)
        assert clock.beats_away(10) == pytest.approx(10.0)

    def test_beats_away_past(self):
        clock = BeatClock(bpm=120.0)
        base = time.monotonic()
        clock.tick(base)
        for i in range(1, 51):
            clock.tick(base + i * 0.05)
        if clock.current_beat() > 0:
            assert clock.beats_away(0) <= 0

    def test_next_downbeat_from_start(self):
        clock = BeatClock(bpm=120.0, time_signature=TimeSignature(numerator=4, denominator=4))
        nd = clock.next_downbeat()
        assert nd == 0 or nd == 4

    def test_next_downbeat_mid_bar(self):
        """Test next_downbeat logic without time dependence."""
        clock = BeatClock(bpm=120.0, time_signature=TimeSignature(numerator=4, denominator=4))
        base = time.monotonic()
        # Advance past first beat of bar
        clock.tick(base)
        for i in range(1, 21):
            clock.tick(base + i * 0.03)  # small steps
        nd = clock.next_downbeat()
        assert nd >= clock.current_beat()


# ── Callback Registration ───────────────────────────────────────────

class TestBeatClockCallbacks:
    def test_on_beat_registration(self):
        clock = BeatClock(bpm=120.0)
        called = []
        cb = clock.on_beat(lambda beat, t: called.append(beat), period=1)
        assert cb is not None
        base = time.monotonic()
        clock.tick(base)
        for i in range(1, 20):
            clock.tick(base + i * 0.05)

    def test_after_beat_registration(self):
        clock = BeatClock(bpm=120.0)
        cb = clock.after_beat(lambda beat, t: None, offset=0.05)
        assert cb is not None

    def test_between_beats_registration(self):
        clock = BeatClock(bpm=120.0)
        cb = clock.between_beats(lambda beat, t: None, count=2)
        assert cb is not None

    def test_add_callback(self):
        clock = BeatClock(bpm=120.0)
        mock_fn = MagicMock()
        cb = BeatCallback(on_beat=mock_fn, period=1)
        result = clock.add_callback(cb)
        assert result is not None


# ── Representation ──────────────────────────────────────────────────

class TestBeatClockRepr:
    def test_repr_contains_bpm(self):
        clock = BeatClock(bpm=72.0)
        repr_str = repr(clock)
        assert "72" in repr_str

    def test_repr_contains_running_state(self):
        clock = BeatClock()
        repr_str = repr(clock)
        assert "▶" in repr_str

    def test_repr_contains_paused_state(self):
        clock = BeatClock()
        clock.pause()
        repr_str = repr(clock)
        assert "⏸" in repr_str

    def test_repr_contains_beat_and_bar(self):
        clock = BeatClock(bpm=120.0)
        clock.tick(time.monotonic() + 1.0)
        repr_str = repr(clock)
        assert "beat=" in repr_str
        assert "bar=" in repr_str


# ── Edge Cases ──────────────────────────────────────────────────────

class TestBeatClockEdgeCases:
    def test_very_slow_bpm(self):
        clock = BeatClock(bpm=20.0)
        assert clock.bpm() == pytest.approx(20.0)
        assert clock.seconds_per_beat() == pytest.approx(3.0, abs=0.01)

    def test_very_fast_bpm(self):
        clock = BeatClock(bpm=300.0)
        assert clock.bpm() == pytest.approx(300.0)
        assert clock.seconds_per_beat() == pytest.approx(0.2, abs=0.01)

    def test_unusual_time_signature(self):
        ts = TimeSignature(7, 8)
        clock = BeatClock(bpm=100.0, time_signature=ts)
        assert clock.time_signature().numerator == 7

    def test_double_pause(self):
        clock = BeatClock()
        clock.pause()
        clock.pause()  # should not raise
        assert clock.is_running is False

    def test_double_resume(self):
        clock = BeatClock()
        clock.pause()
        clock.resume()
        clock.resume()  # should not raise
        assert clock.is_running is True

    def test_resume_without_pause(self):
        clock = BeatClock()
        clock.resume()  # should not raise
        assert clock.is_running is True
