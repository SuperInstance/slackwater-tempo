"""
Comprehensive tests for GrooveEngine — the feel of the beat.

Tests cover:
- Swing factor and swing offset
- Push/drag timing
- Humanization
- Combined timing_offset
- Game state presets
- Groove detection (is_in_the_pocket)
- Agent-specific grooves
- Edge cases
"""

import pytest
import random

from slackwater_tempo import GrooveEngine, GameState, TempoMap, TempoPreset
from slackwater_tempo.groove import PRESETS, TempoPreset as TP


# ── Construction & Defaults ─────────────────────────────────────────

class TestGrooveConstruction:
    def test_default_construction(self):
        g = GrooveEngine()
        assert g.swing == 0.0
        assert g.push_drag_ms == 0.0
        assert g.humanize_ms == 0.0
        assert g.current_preset is None

    def test_custom_construction(self):
        g = GrooveEngine(swing=0.6, push_drag_ms=-3.0, humanize_ms=2.0)
        assert g.swing == 0.6
        assert g.push_drag_ms == -3.0
        assert g.humanize_ms == 2.0


# ── Setters & Clamping ──────────────────────────────────────────────

class TestGrooveSetters:
    def test_set_swing(self):
        g = GrooveEngine()
        g.set_swing(0.55)
        assert g.swing == 0.55

    def test_swing_clamped_high(self):
        g = GrooveEngine()
        g.set_swing(2.0)
        assert g.swing == 1.0

    def test_swing_clamped_low(self):
        g = GrooveEngine()
        g.set_swing(-1.0)
        assert g.swing == 0.0

    def test_set_push_drag(self):
        g = GrooveEngine()
        g.set_push_drag(5.0)
        assert g.push_drag_ms == 5.0

    def test_push_drag_clamped_high(self):
        g = GrooveEngine()
        g.set_push_drag(50.0)
        assert g.push_drag_ms == 10.0

    def test_push_drag_clamped_low(self):
        g = GrooveEngine()
        g.set_push_drag(-50.0)
        assert g.push_drag_ms == -10.0

    def test_set_humanize(self):
        g = GrooveEngine()
        g.set_humanize(5.0)
        assert g.humanize_ms == 5.0

    def test_humanize_clamped_zero(self):
        g = GrooveEngine()
        g.set_humanize(-5.0)
        assert g.humanize_ms == 0.0


# ── Swing Offset ────────────────────────────────────────────────────

class TestSwingOffset:
    def test_no_swing_returns_zero(self):
        g = GrooveEngine(swing=0.0)
        assert g.swing_offset(0) == 0.0
        assert g.swing_offset(1) == 0.0

    def test_downbeat_no_swing(self):
        """Even beats (downbeats) should not be swung."""
        g = GrooveEngine(swing=0.6)
        assert g.swing_offset(0) == 0.0
        assert g.swing_offset(2) == 0.0

    def test_offbeat_gets_swing(self):
        """Odd beats should be delayed by swing."""
        g = GrooveEngine(swing=0.6)
        offset = g.swing_offset(1)
        assert offset > 0.0
        # Max swing delay = swing * (1/3) ≈ 0.2 at swing=0.6
        assert offset == pytest.approx(0.6 / 3.0)

    def test_full_swing(self):
        g = GrooveEngine(swing=1.0)
        offset = g.swing_offset(1)
        assert offset == pytest.approx(1.0 / 3.0)

    def test_swing_offset_symmetry(self):
        """Odd beats all get the same swing."""
        g = GrooveEngine(swing=0.5)
        assert g.swing_offset(1) == g.swing_offset(3)


# ── Timing Offset (Combined) ────────────────────────────────────────

class TestTimingOffset:
    def test_zero_groove_zero_offset(self):
        g = GrooveEngine()
        assert g.timing_offset() == 0.0

    def test_push_drag_only(self):
        g = GrooveEngine(push_drag_ms=5.0)
        offset = g.timing_offset(beat_in_bar=0)
        assert offset == pytest.approx(0.005)  # 5ms in seconds

    def test_swing_only(self):
        g = GrooveEngine(swing=0.6)
        offset = g.timing_offset(beat_in_bar=1)
        assert offset > 0.0
        # Should include swing delay but not push/drag
        assert offset == pytest.approx(0.6 / 3.0, abs=0.001)

    def test_is_off_beat_flag(self):
        """is_off_beat should trigger swing even on even beats."""
        g = GrooveEngine(swing=0.6)
        offset = g.timing_offset(beat_in_bar=0, is_off_beat=True)
        assert offset > 0.0

    def test_combined_swing_and_push_drag(self):
        g = GrooveEngine(swing=0.6, push_drag_ms=-3.0)
        offset = g.timing_offset(beat_in_bar=1)
        # swing offset = 0.2, push/drag = -0.003
        assert offset == pytest.approx(0.2 - 0.003, abs=0.001)

    def test_humanize_within_bounds(self):
        """Humanized offset should be within ±humanize_ms."""
        g = GrooveEngine(humanize_ms=10.0)
        offsets = [g.timing_offset() for _ in range(100)]
        for o in offsets:
            assert abs(o) <= 0.011  # 10ms + small epsilon

    def test_humanize_zero_is_deterministic(self):
        """Without humanization, timing_offset is deterministic."""
        g = GrooveEngine(swing=0.5, push_drag_ms=2.0)
        o1 = g.timing_offset(beat_in_bar=1)
        o2 = g.timing_offset(beat_in_bar=1)
        assert o1 == o2


# ── Game State Presets ──────────────────────────────────────────────

class TestGamePresets:
    def test_all_states_have_presets(self):
        for state in GameState:
            assert state in PRESETS

    def test_preset_values_are_distinct(self):
        bpms = [p.bpm for p in PRESETS.values()]
        assert len(bpms) == len(set(bpms))  # all unique

    def test_calm_is_slowest(self):
        assert PRESETS[GameState.CALM].bpm < PRESETS[GameState.STEADY].bpm

    def test_urgent_is_fastest(self):
        assert PRESETS[GameState.URGENT].bpm > PRESETS[GameState.ACTIVE].bpm

    def test_apply_preset_sets_bpm_target(self):
        g = GrooveEngine()
        tempo = TempoMap(bpm=120.0)
        preset = g.apply_preset(GameState.CALM, tempo)
        assert preset.name == "Adagio"
        assert g.current_preset is not None
        assert g.current_preset.state == GameState.CALM

    def test_apply_preset_returns_preset(self):
        g = GrooveEngine()
        tempo = TempoMap(bpm=120.0)
        preset = g.apply_preset(GameState.URGENT, tempo)
        assert isinstance(preset, TempoPreset)
        assert preset.bpm == 168.0

    def test_get_preset_without_applying(self):
        g = GrooveEngine()
        preset = g.get_preset(GameState.ACTIVE)
        assert preset.name == "Allegro"
        # Should NOT have set current_preset
        assert g.current_preset is None

    def test_preset_characters_are_meaningful(self):
        """Every preset should have a non-trivial character description."""
        for state, preset in PRESETS.items():
            assert len(preset.character) > 10
            assert preset.name  # Italian marking exists


# ── Groove Detection: In The Pocket ─────────────────────────────────

class TestInPocket:
    def test_default_not_in_pocket(self):
        """No swing = not in pocket."""
        g = GrooveEngine()
        assert g.is_in_the_pocket() is False

    def test_classic_jazz_in_pocket(self):
        """Swing ~0.6, subtle push/drag = in the pocket."""
        g = GrooveEngine(swing=0.6, push_drag_ms=3.0)
        assert g.is_in_the_pocket() is True

    def test_too_much_swing_not_in_pocket(self):
        g = GrooveEngine(swing=0.85)
        assert g.is_in_the_pocket() is False

    def test_too_much_push_not_in_pocket(self):
        g = GrooveEngine(swing=0.55, push_drag_ms=8.0)
        assert g.is_in_the_pocket() is False

    def test_boundary_swing_045(self):
        g = GrooveEngine(swing=0.45, push_drag_ms=0.0)
        assert g.is_in_the_pocket() is True

    def test_boundary_swing_070(self):
        g = GrooveEngine(swing=0.70, push_drag_ms=0.0)
        assert g.is_in_the_pocket() is True

    def test_boundary_push_drag_5ms(self):
        g = GrooveEngine(swing=0.55, push_drag_ms=5.0)
        assert g.is_in_the_pocket() is True


# ── Agent Grooves ───────────────────────────────────────────────────

class TestAgentGrooves:
    def test_lucineer_groove(self):
        g = GrooveEngine()
        groove = g.agent_groove("lucineer")
        assert groove["swing"] == 0.55
        assert groove["push_drag_ms"] > 0  # behind the beat

    def test_earl_groove(self):
        g = GrooveEngine()
        groove = g.agent_groove("earl")
        assert groove["push_drag_ms"] < 0  # ahead of the beat

    def test_player_groove_is_neutral(self):
        g = GrooveEngine()
        groove = g.agent_groove("player")
        assert groove["swing"] == 0.0
        assert groove["push_drag_ms"] == 0.0

    def test_unknown_agent_defaults_to_player(self):
        g = GrooveEngine()
        groove = g.agent_groove("nobody")
        assert groove["swing"] == 0.0

    def test_apply_agent_groove(self):
        g = GrooveEngine()
        g.apply_agent_groove("lucineer")
        assert g.swing == 0.55
        assert g.push_drag_ms == 4.0
        assert g.humanize_ms == 2.0

    def test_apply_earl_groove(self):
        g = GrooveEngine()
        g.apply_agent_groove("earl")
        assert g.swing == 0.50
        assert g.push_drag_ms == -3.0

    def test_agent_grooves_have_character(self):
        g = GrooveEngine()
        for name in ["lucineer", "earl", "player"]:
            groove = g.agent_groove(name)
            assert "character" in groove
            assert len(groove["character"]) > 5


# ── TempoPreset Dataclass ───────────────────────────────────────────

class TestTempoPreset:
    def test_preset_is_frozen(self):
        """TempoPreset is frozen dataclass."""
        p = TempoPreset(
            name="Test",
            bpm=100.0,
            character="Testing",
            state=GameState.CALM,
        )
        with pytest.raises(AttributeError):
            p.bpm = 200.0

    def test_preset_str(self):
        p = TempoPreset(
            name="Allegro",
            bpm=132.0,
            character="Fast and lively",
            state=GameState.ACTIVE,
        )
        s = str(p)
        assert "Allegro" in s
        assert "132" in s
        assert "Fast" in s


# ── Repr ────────────────────────────────────────────────────────────

class TestGrooveRepr:
    def test_repr_contains_swing(self):
        g = GrooveEngine(swing=0.55)
        assert "0.55" in repr(g)

    def test_repr_contains_push_drag(self):
        g = GrooveEngine(push_drag_ms=-3.0)
        r = repr(g)
        assert "-3" in r or "+-3" in r or "+-3.0" in r

    def test_repr_shows_pocket_status(self):
        g = GrooveEngine(swing=0.6, push_drag_ms=2.0)
        r = repr(g)
        assert "in the pocket" in r

    def test_repr_no_pocket(self):
        g = GrooveEngine()
        r = repr(g)
        assert "in the pocket" not in r

    def test_repr_shows_preset_when_set(self):
        g = GrooveEngine()
        tempo = TempoMap(bpm=120.0)
        g.apply_preset(GameState.CALM, tempo)
        r = repr(g)
        assert "Adagio" in r
