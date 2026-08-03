# slackwater-tempo

> In MIDI, the tempo is the first class citizen that everything else depends on; as is life.

A tempo-first engine for the Slackwater unified framework. Built on the insight that tempo is not speed — it is the *character of time*.

## Modules

- **`tempo.TempoMap`** — BPM tracking with smooth transitions (accelerando/ritardando), time signatures, beat scheduling callbacks
- **`groove.GrooveEngine`** — Swing, push/drag micro-timing, game-state tempo presets (Adagio, Andante, Allegro, Presto)
- **`energy.EnergyAdapter`** — Observes player behavior and maps it to BPM with smooth 5-10s transitions
- **`clock.BeatClock`** — Shared clock that all agents sync to

## Install

```bash
pip install -e ".[dev]"
```

## Test

```bash
python3 -m pytest tests/ -v
```

## Philosophy

Every system has a tempo. The question is whether it was composed or inherited from a metronome.
