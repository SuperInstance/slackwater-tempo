"""
Smoke tests for slackwater-tempo.

These tests verify that the core modules import, construct, and
behave correctly for basic scenarios. They are not exhaustive —
they are the "does it tick?" check. The deep musical behaviour
is tested by ear, in the game, when the build lands on the beat
and the player feels it.
"""

import time

import pytest

from slackwater_tempo import (
    TempoMap,
    BeatClock,
    GrooveEngine,
    EnergyAdapter,
    PlayerBehavior,
    GameState,
    TempoPreset,
    TimeSignature,
    TransitionCurve,
    BeatCallback,
)
from slackwater_tempo.groove import PRESETS


# ── TempoMap ────────────────────────────────────────────────────────

class TestTempoMap:
    def test_construction(self):
        t = TempoMap(bpm=120)
        assert t.bpm == 120.0
        assert t.beat == 0
        assert t.bar == 0

    def test_invalid_bpm(self):
        with pytest.raises(ValueError):
            TempoMap(bpm=0)
        with pytest.raises(ValueError):
            TempoMap(bpm=-10)

    def test_time_signature(self):
        ts = TimeSignature(3, 4)
        t = TempoMap(bpm=100, time_signature=ts)
        assert t.time_signature.numerator == 3
        assert t.time_signature.beats_per_bar == 3

    def test_invalid_time_signature(self):
        with pytest.raises(ValueError):
            TimeSignature(0, 4)
        with pytest.raises(ValueError):
            TimeSignature(3, 3)  # denominator must be power of 2

    def test_immediate_bpm_change(self):
        t = TempoMap(bpm=120)
        t.set_bpm(140)
        assert t.bpm == 140.0
        assert not t.is_transitioning

    def test_smooth_bpm_change(self):
        t = TempoMap(bpm=120)
        t.set_bpm(140, transition_time=0.5)
        # During transition
        assert t.is_transitioning
        # After enough time
        time.sleep(0.6)
        assert t.bpm == pytest.approx(140.0, abs=0.1)
        assert not t.is_transitioning

    def test_accelerando(self):
        t = TempoMap(bpm=80)
        t.accelerando(120, duration=0.3)
        assert t.is_transitioning
        time.sleep(0.35)
        assert t.bpm == pytest.approx(120.0, abs=0.5)

    def test_ritardando(self):
        t = TempoMap(bpm=140)
        t.ritardando(80, duration=0.3)
        assert t.is_transitioning
        time.sleep(0.35)
        assert t.bpm == pytest.approx(80.0, abs=0.5)

    def test_accelerando_wrong_direction(self):
        t = TempoMap(bpm=120)
        with pytest.raises(ValueError):
            t.accelerando(80)  # target slower = should be ritardando

    def test_beat_advances(self):
        t = TempoMap(bpm=600)  # 10 beats/sec for fast test
        start = time.monotonic()
        t.update(start)         # initialise
        time.sleep(0.25)        # ~2.5 beats
        t.update(time.monotonic())
        assert t.beat >= 2

    def test_bar_advances(self):
        t = TempoMap(bpm=600, time_signature=TimeSignature(4, 4))
        now = time.monotonic()
        t.update(now)
        time.sleep(0.45)  # ~4.5 beats = just over 1 bar
        t.update(time.monotonic())
        assert t.bar >= 1

    def test_on_beat_callback(self):
        t = TempoMap(bpm=600)  # 10 beats/sec
        fired = []
        t.on_beat(lambda beat, ts: fired.append(beat))
        now = time.monotonic()
        t.update(now)
        time.sleep(0.25)
        t.update(time.monotonic())
        assert len(fired) >= 2
        assert fired[0] >= 1  # first beat is beat 1

    def test_on_beat_period(self):
        t = TempoMap(bpm=600)
        fired = []
        t.on_beat(lambda beat, ts: fired.append(beat), period=2)
        now = time.monotonic()
        t.update(now)
        time.sleep(0.35)  # ~3.5 beats
        t.update(time.monotonic())
        # With period=2, only beats 2 and 4 should fire
        assert all(b % 2 == 0 for b in fired)

    def test_beat_phase(self):
        t = TempoMap(bpm=120)
        now = time.monotonic()
        t.update(now)
        # Right after init, phase should be ~0
        assert 0.0 <= t.beat_phase() <= 1.0

    def test_repr(self):
        t = TempoMap(bpm=120)
        s = repr(t)
        assert "120" in s
        assert "BPM" in s


# ── BeatClock ───────────────────────────────────────────────────────

class TestBeatClock:
    def test_construction(self):
        c = BeatClock(bpm=100)
        assert c.bpm() == 100.0
        assert c.current_beat() == 0

    def test_tick_advances(self):
        c = BeatClock(bpm=600)
        c.tick()  # initialise
        time.sleep(0.15)
        c.tick()
        assert c.current_beat() >= 1

    def test_downbeat_detection(self):
        c = BeatClock(bpm=600, time_signature=TimeSignature(4, 4))
        c.tick()
        time.sleep(0.45)  # ~4.5 beats
        c.tick()
        # Should be into the next bar
        # The next downbeat should be at beat 8
        assert c.next_downbeat() >= 4

    def test_pause_resume(self):
        c = BeatClock(bpm=600)
        c.tick()
        time.sleep(0.1)
        c.tick()
        beat_before_pause = c.current_beat()

        c.pause()
        time.sleep(0.2)
        c.tick()  # should be a no-op
        assert c.current_beat() == beat_before_pause

        c.resume()
        time.sleep(0.1)
        c.tick()
        # Should have advanced after resume
        assert c.current_beat() > beat_before_pause

    def test_on_beat_via_clock(self):
        c = BeatClock(bpm=600)
        fired = []
        c.on_beat(lambda beat, ts: fired.append(beat))
        c.tick()
        time.sleep(0.2)
        c.tick()
        assert len(fired) >= 1

    def test_set_bpm(self):
        c = BeatClock(bpm=120)
        c.set_bpm(140)
        assert c.bpm() == 140.0

    def test_repr(self):
        c = BeatClock(bpm=120)
        s = repr(c)
        assert "120" in s


# ── GrooveEngine ────────────────────────────────────────────────────

class TestGrooveEngine:
    def test_construction(self):
        g = GrooveEngine()
        assert g.swing == 0.0
        assert g.push_drag_ms == 0.0

    def test_swing_clamped(self):
        g = GrooveEngine()
        g.set_swing(5.0)
        assert g.swing == 1.0
        g.set_swing(-1.0)
        assert g.swing == 0.0

    def test_push_drag_clamped(self):
        g = GrooveEngine()
        g.set_push_drag(50.0)
        assert g.push_drag_ms == 10.0
        g.set_push_drag(-50.0)
        assert g.push_drag_ms == -10.0

    def test_timing_offset_no_groove(self):
        g = GrooveEngine()  # straight, no push/drag
        assert g.timing_offset() == 0.0

    def test_timing_offset_swing(self):
        g = GrooveEngine(swing=1.0)
        off = g.timing_offset(beat_in_bar=1)  # off-beat
        assert off > 0.0
        on = g.timing_offset(beat_in_bar=0)   # downbeat
        assert on == 0.0

    def test_timing_offset_push_drag(self):
        g = GrooveEngine(push_drag_ms=5.0)
        offset = g.timing_offset()
        assert offset == pytest.approx(0.005, abs=0.0001)

    def test_humanization_within_bounds(self):
        g = GrooveEngine(humanize_ms=3.0)
        offsets = [g.timing_offset() for _ in range(100)]
        assert all(abs(o) <= 0.003 + 0.001 for o in offsets)  # small float tolerance

    def test_apply_preset(self):
        t = TempoMap(bpm=120)
        g = GrooveEngine()
        preset = g.apply_preset(GameState.CALM, t, transition_time=0.0)
        assert preset.name == "Adagio"
        assert t.bpm == pytest.approx(66.0)

    def test_all_presets_exist(self):
        for state in GameState:
            preset = PRESETS[state]
            assert preset.name in ("Adagio", "Andante", "Allegro", "Presto")
            assert preset.bpm > 0
            assert len(preset.character) > 0

    def test_in_the_pocket(self):
        g = GrooveEngine(swing=0.55, push_drag_ms=3.0)
        assert g.is_in_the_pocket()

        g.set_swing(0.9)
        assert not g.is_in_the_pocket()

        g.set_swing(0.55)
        g.set_push_drag(8.0)
        assert not g.is_in_the_pocket()

    def test_agent_groove(self):
        g = GrooveEngine()
        g.apply_agent_groove("lucineer")
        assert g.swing == pytest.approx(0.55)
        assert g.push_drag_ms == pytest.approx(4.0)

        g.apply_agent_groove("earl")
        assert g.push_drag_ms == pytest.approx(-3.0)


# ── EnergyAdapter ───────────────────────────────────────────────────

class TestEnergyAdapter:
    def test_construction(self):
        t = TempoMap(bpm=72)
        adapter = EnergyAdapter(t)
        assert adapter.current_energy == 0.0

    def test_observe_changes_target(self):
        t = TempoMap(bpm=72)
        adapter = EnergyAdapter(t)
        adapter.observe(PlayerBehavior(build_rate=60, action_rate=30))
        assert adapter.target_energy > 0.0

    def test_energy_to_bpm_bounds(self):
        t = TempoMap(bpm=72)
        adapter = EnergyAdapter(t)
        assert adapter.energy_to_bpm(0.0) == adapter.min_bpm
        assert adapter.energy_to_bpm(1.0) == adapter.max_bpm

    def test_energy_to_bpm_monotonic(self):
        t = TempoMap(bpm=72)
        adapter = EnergyAdapter(t)
        bpm_low = adapter.energy_to_bpm(0.2)
        bpm_mid = adapter.energy_to_bpm(0.5)
        bpm_high = adapter.energy_to_bpm(0.8)
        assert bpm_low < bpm_mid < bpm_high

    def test_activity_levels(self):
        # IDLE
        idle = PlayerBehavior(idle_time=30, build_rate=0, action_rate=0)
        assert idle.activity_level() == ActivityLevel.IDLE

        # RELAXED
        relaxed = PlayerBehavior(build_rate=2, action_rate=1)
        assert relaxed.activity_level() == ActivityLevel.RELAXED

        # FRANTIC
        frantic = PlayerBehavior(build_rate=100, action_rate=50, chat_frequency=20)
        assert frantic.activity_level() == ActivityLevel.FRANTIC

    def test_smooth_update(self):
        t = TempoMap(bpm=60)
        adapter = EnergyAdapter(t, smoothing_seconds=0.1)
        adapter.observe(PlayerBehavior(build_rate=100, action_rate=50))
        # First update initialises
        adapter.update(time.monotonic())
        # After some time, energy should have moved toward target
        time.sleep(0.15)
        adapter.update(time.monotonic())
        assert adapter.current_energy > 0.0

    def test_bpm_eventually_changes(self):
        t = TempoMap(bpm=60)
        adapter = EnergyAdapter(t, smoothing_seconds=0.05, _min_change_interval=0.0)
        # Override the min change interval for testing
        adapter._min_change_interval = 0.0
        adapter.observe(PlayerBehavior(build_rate=120, action_rate=60, chat_frequency=30))
        now = time.monotonic()
        adapter.update(now)
        time.sleep(0.2)
        adapter.update(time.monotonic())
        time.sleep(0.2)
        adapter.update(time.monotonic())
        # BPM should have changed from 60
        assert t.bpm > 60.0

    def test_idle_reduces_energy(self):
        pb1 = PlayerBehavior(build_rate=30, action_rate=15, idle_time=0)
        pb2 = PlayerBehavior(build_rate=30, action_rate=15, idle_time=30)
        assert pb2.energy < pb1.energy


# Need ActivityLevel import for test
from slackwater_tempo.energy import ActivityLevel


# ── Integration ─────────────────────────────────────────────────────

class TestIntegration:
    def test_full_pipeline(self):
        """Wire all four modules together."""
        clock = BeatClock(bpm=72)
        groove = GrooveEngine(swing=0.55, push_drag_ms=2.0)
        groove.apply_preset(GameState.STEADY, clock.tempo_map, transition_time=0.1)
        adapter = EnergyAdapter(clock.tempo_map, smoothing_seconds=0.1)
        adapter._min_change_interval = 0.0

        # Observe high-energy behaviour
        adapter.observe(PlayerBehavior(build_rate=80, action_rate=40, chat_frequency=10))

        # Run a few frames
        for _ in range(10):
            now = time.monotonic()
            adapter.update(now)
            clock.tick(now)
            time.sleep(0.05)

        # The BPM should have shifted from the initial 92 (Andante)
        assert clock.bpm() != pytest.approx(92.0, abs=1.0)

    def test_groove_presets_match_essay(self):
        """Verify the presets match the tempo map essay's character descriptions."""
        assert PRESETS[GameState.CALM].name == "Adagio"
        assert PRESETS[GameState.STEADY].name == "Andante"
        assert PRESETS[GameState.ACTIVE].name == "Allegro"
        assert PRESETS[GameState.URGENT].name == "Presto"
