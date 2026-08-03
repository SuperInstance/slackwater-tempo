# Slackwater Tempo

*Tempo is the first-class citizen that everything else depends on. As is life.*

A Python package that provides the shared tempo map for the Slackwater ecosystem. Every agent, every build, every interaction lives on the same tempo. The tempo adapts to the player's energy. The groove is real.

## What it does

- **TempoMap**: a global BPM that all agents share, with smooth transitions (not jumps)
- **GrooveEngine**: swing factor, push/drag micro-timing, human feel
- **EnergyAdapter**: watches player behavior and adjusts tempo (fast building = accelerando, contemplation = ritardando)
- **BeatClock**: the shared clock that all other modules sync to
- **EventScheduler**: schedule events on the beat, off the beat, or between beats

## Install

```bash
pip install slackwater-tempo
```

## Use

```python
from slackwater_tempo import TempoMap, EnergyAdapter

tempo = TempoMap(initial_bpm=72)  # Adagio — contemplative morning
adapter = EnergyAdapter(tempo)

# When player builds fast, tempo rises
adapter.observe(build_rate=2.5, idle_time=0.3)
# tempo.bpm → 78 (gentle accelerando)

# When player pauses to think, tempo settles
adapter.observe(build_rate=0.0, idle_time=15.0)
# tempo.bpm → 68 (ritardando to restful)

# Schedule an event on the next downbeat
tempo.on_beat(lambda: place_part("Capstone"), beat=1)
```

## The Philosophy

From Casey's insight: "In MIDI, the tempo is the first class citizen that everything else depends on; as is life."

A heartbeat is a tempo. Breathing is a tempo. The tide is a tempo. When agents share a tempo map, they're not just coordinated — they're alive in the same time.

## Related

- [Slackwater Perception](https://github.com/SuperInstance/slackwater-perception) — multi-track MIDI world encoding
- [Slackwater Lattice](https://github.com/SuperInstance/slackwater-lattice) — Eisenstein A₂ build placement
- [Slackwater T-Minus](https://github.com/SuperInstance/slackwater-tminus) — predict-and-confirm timing
- [Slackwater Harmony](https://github.com/SuperInstance/slackwater-harmony) — cognitive adaptation
- [Lucineer](https://github.com/SuperInstance/lucineer-system) — the game these modules power
