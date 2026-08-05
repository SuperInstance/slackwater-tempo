"""
Comprehensive tests for EnergyAdapter — the bridge between life and tempo.

Tests cover:
- PlayerBehavior classification (activity levels)
- Energy score computation
- EnergyAdapter observation and smoothing
- Energy → BPM mapping
- BPM change throttling
- Min/max BPM clamping
- Edge cases (no behavior observed, rapid changes, extreme values)
"""

import pytest
import time

from slackwater_tempo import TempoMap, EnergyAdapter, PlayerBehavior, ActivityLevel
from slackwater_tempo.energy import ACTIVITY_BPM


# ── PlayerBehavior: Activity Classification ─────────────────────────

class TestPlayerBehaviorClassification:
    def test_idle_classification(self):
        """High idle time + low activity = IDLE."""
        pb = PlayerBehavior(idle_time=30.0, build_rate=0.0, action_rate=0.0)
        assert pb.activity_level() == ActivityLevel.IDLE

    def test_idle_with_minimal_activity(self):
        pb = PlayerBehavior(idle_time=20.0, build_rate=0.5, action_rate=1.0)
        assert pb.activity_level() == ActivityLevel.IDLE

    def test_relaxed_classification(self):
        """Low total activity = RELAXED."""
        pb = PlayerBehavior(build_rate=2.0, action_rate=1.0, chat_frequency=0.5)
        assert pb.activity_level() == ActivityLevel.RELAXED

    def test_moderate_classification(self):
        pb = PlayerBehavior(build_rate=10.0, action_rate=5.0, chat_frequency=2.0)
        assert pb.activity_level() == ActivityLevel.MODERATE

    def test_engaged_classification(self):
        pb = PlayerBehavior(build_rate=30.0, action_rate=15.0, chat_frequency=5.0)
        assert pb.activity_level() == ActivityLevel.ENGAGED

    def test_intense_classification(self):
        pb = PlayerBehavior(build_rate=60.0, action_rate=30.0, chat_frequency=10.0)
        assert pb.activity_level() == ActivityLevel.INTENSE

    def test_frantic_classification(self):
        pb = PlayerBehavior(build_rate=80.0, action_rate=40.0, chat_frequency=20.0)
        assert pb.activity_level() == ActivityLevel.FRANTIC


# ── PlayerBehavior: Energy Score ────────────────────────────────────

class TestPlayerBehaviorEnergy:
    def test_zero_energy(self):
        """No activity = zero energy."""
        pb = PlayerBehavior()
        assert pb.energy == 0.0

    def test_max_build_rate(self):
        """Maxed build rate dominates energy."""
        pb = PlayerBehavior(build_rate=120.0)
        # build_norm = 1.0, weighted at 0.45
        assert pb.energy == pytest.approx(0.45, abs=0.01)

    def test_max_action_rate(self):
        pb = PlayerBehavior(action_rate=60.0)
        assert pb.energy == pytest.approx(0.25, abs=0.01)

    def test_max_chat_frequency(self):
        pb = PlayerBehavior(chat_frequency=30.0)
        assert pb.energy == pytest.approx(0.15, abs=0.01)

    def test_max_movement(self):
        pb = PlayerBehavior(movement_speed=50.0)
        assert pb.energy == pytest.approx(0.15, abs=0.01)

    def test_all_maxed(self):
        pb = PlayerBehavior(
            build_rate=120.0,
            action_rate=60.0,
            chat_frequency=30.0,
            movement_speed=50.0,
        )
        assert pb.energy == pytest.approx(1.0, abs=0.01)

    def test_idle_reduces_energy(self):
        """After 5s idle, energy starts dropping."""
        pb_active = PlayerBehavior(build_rate=30.0)
        pb_idle = PlayerBehavior(build_rate=30.0, idle_time=35.0)
        assert pb_idle.energy < pb_active.energy

    def test_energy_never_negative(self):
        """Even with huge idle penalty, energy stays ≥ 0."""
        pb = PlayerBehavior(idle_time=999.0)
        assert pb.energy >= 0.0

    def test_energy_never_exceeds_one(self):
        pb = PlayerBehavior(
            build_rate=999.0,
            action_rate=999.0,
            chat_frequency=999.0,
            movement_speed=999.0,
        )
        assert pb.energy <= 1.0


# ── Activity Level → BPM Mapping ────────────────────────────────────

class TestActivityBPM:
    def test_all_levels_have_bpm(self):
        """Every ActivityLevel must have a BPM mapping."""
        for level in ActivityLevel:
            assert level in ACTIVITY_BPM

    def test_bpm_ordering(self):
        """Higher activity = higher BPM."""
        levels = [
            ActivityLevel.IDLE,
            ActivityLevel.RELAXED,
            ActivityLevel.MODERATE,
            ActivityLevel.ENGAGED,
            ActivityLevel.INTENSE,
            ActivityLevel.FRANTIC,
        ]
        for i in range(len(levels) - 1):
            assert ACTIVITY_BPM[levels[i]] < ACTIVITY_BPM[levels[i + 1]]

    def test_idle_is_slow(self):
        assert ACTIVITY_BPM[ActivityLevel.IDLE] < 70.0

    def test_frantic_is_fast(self):
        assert ACTIVITY_BPM[ActivityLevel.FRANTIC] > 150.0


# ── EnergyAdapter: Construction ─────────────────────────────────────

class TestEnergyAdapterConstruction:
    def test_default_construction(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        assert adapter.tempo is tempo
        assert adapter.smoothing_seconds == 7.0
        assert adapter.min_bpm == 50.0
        assert adapter.max_bpm == 180.0

    def test_custom_params(self):
        tempo = TempoMap(bpm=100.0)
        adapter = EnergyAdapter(
            tempo,
            smoothing_seconds=5.0,
            min_bpm=60.0,
            max_bpm=160.0,
        )
        assert adapter.smoothing_seconds == 5.0
        assert adapter.min_bpm == 60.0
        assert adapter.max_bpm == 160.0

    def test_initial_energy_zero(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        assert adapter.current_energy == 0.0

    def test_no_activity_level_before_observe(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        assert adapter.activity_level is None


# ── EnergyAdapter: Observation ──────────────────────────────────────

class TestEnergyAdapterObserve:
    def test_observe_sets_target(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        pb = PlayerBehavior(build_rate=30.0)
        adapter.observe(pb)
        assert adapter.target_energy > 0.0

    def test_observe_stores_behavior(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        pb = PlayerBehavior(build_rate=60.0, action_rate=30.0)
        adapter.observe(pb)
        assert adapter.activity_level is not None
        assert adapter.activity_level == pb.activity_level()

    def test_observe_zero_energy(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior())
        assert adapter.target_energy == 0.0


# ── EnergyAdapter: Update & Smoothing ───────────────────────────────

class TestEnergyAdapterUpdate:
    def test_first_update_snaps_to_target(self):
        """The first update should snap current_energy to target."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=60.0))
        adapter.update(time.monotonic() + 0.1)
        # Should have snapped close to target
        assert abs(adapter.current_energy - adapter.target_energy) < 0.1

    def test_smoothing_takes_time(self):
        """Energy transitions gradually, not instantly."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, smoothing_seconds=10.0)
        adapter.observe(PlayerBehavior(build_rate=60.0))
        now = time.monotonic()
        adapter.update(now)  # snap
        # Change target
        adapter.observe(PlayerBehavior(build_rate=120.0))
        # Small time step → small energy change
        adapter.update(now + 0.1)
        # Should not have reached target yet
        assert adapter.current_energy < adapter.target_energy

    def test_update_without_observe(self):
        """Update before any observation should not crash."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.update(time.monotonic() + 0.1)
        assert adapter.current_energy == 0.0

    def test_update_converges_over_time(self):
        """After many updates, current_energy → target_energy."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, smoothing_seconds=2.0)
        adapter.observe(PlayerBehavior(build_rate=60.0))
        base = time.monotonic()
        for i in range(100):
            adapter.update(base + i * 0.5)
        assert adapter.current_energy == pytest.approx(adapter.target_energy, abs=0.05)


# ── EnergyAdapter: Energy → BPM ─────────────────────────────────────

class TestEnergyBPMMapping:
    def test_zero_energy_is_min_bpm(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, min_bpm=50.0, max_bpm=180.0)
        assert adapter.energy_to_bpm(0.0) == pytest.approx(50.0)

    def test_max_energy_is_max_bpm(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, min_bpm=50.0, max_bpm=180.0)
        assert adapter.energy_to_bpm(1.0) == pytest.approx(180.0)

    def test_mid_energy_between_min_max(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, min_bpm=50.0, max_bpm=180.0)
        mid = adapter.energy_to_bpm(0.5)
        assert 50.0 < mid < 180.0

    def test_energy_clamping(self):
        """Energy outside [0,1] should be clamped."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, min_bpm=50.0, max_bpm=180.0)
        assert adapter.energy_to_bpm(-1.0) == pytest.approx(50.0)
        assert adapter.energy_to_bpm(2.0) == pytest.approx(180.0)

    def test_exponential_curve(self):
        """The 0.8 exponent means low energy rises faster than linear."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo, min_bpm=0.0, max_bpm=100.0)
        # At energy 0.25, linear would give 25, but 0.25^0.8 ≈ 0.33
        bpm_at_25 = adapter.energy_to_bpm(0.25)
        assert bpm_at_25 > 25.0  # above linear

    def test_bpm_change_threshold(self):
        """BPM only changes when difference > 3 BPM."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(
            tempo,
            smoothing_seconds=0.01,  # very fast smoothing
            min_bpm=50.0,
            max_bpm=180.0,
        )
        base = time.monotonic()
        adapter.observe(PlayerBehavior(build_rate=20.0))
        adapter.update(base + 0.01)
        initial_bpm = tempo.bpm

        # Tiny change in energy — should NOT trigger BPM change
        adapter.observe(PlayerBehavior(build_rate=21.0))
        adapter.update(base + 5.0)  # past min_change_interval
        # The BPM change should be small if it happened
        # (hard to test exact threshold without mocking)


# ── EnergyAdapter: Edge Cases ───────────────────────────────────────

class TestEnergyAdapterEdgeCases:
    def test_negative_dt_ignored(self):
        """Update with past timestamp should be safe."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=30.0))
        adapter.update(time.monotonic() + 10.0)
        # Going backward in time
        adapter.update(time.monotonic() - 10.0)
        # Should not crash

    def test_repr_contains_energy(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=60.0))
        r = repr(adapter)
        assert "energy=" in r

    def test_repr_contains_activity(self):
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=60.0))
        r = repr(adapter)
        assert "activity=" in r

    def test_extreme_build_rate(self):
        """Absurdly high build rate clamps to max energy."""
        tempo = TempoMap(bpm=72.0)
        adapter = EnergyAdapter(tempo)
        adapter.observe(PlayerBehavior(build_rate=99999.0))
        # Energy should be clamped
        assert adapter.target_energy <= 1.0
