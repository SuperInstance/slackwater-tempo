# slackwater-tempo

![tests](https://img.shields.io/badge/tests-43%20passed-brightgreen)
![version](https://img.shields.io/badge/version-0.1.0-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)

Tempo is the first-class citizen that everything else depends on. This package provides BPM tracking with smooth transitions (accelerando / ritardando), time-signature support, groove shaping (swing, push/drag, humanization), game-state tempo presets, player-behavior-to-BPM energy mapping, and a shared beat clock for agent synchronization.

## Installation

```bash
pip install slackwater-tempo
```

## Architecture

```
EnergyAdapter ──observes──▶ PlayerBehavior
       │
       ▼
   TempoMap ◀── GrooveEngine (swing, push/drag, presets)
       │
       ▼
  BeatClock (shared sync)
```

The `BeatClock` owns a `TempoMap` and provides convenience methods. The `EnergyAdapter` reads player telemetry and drives BPM transitions. The `GrooveEngine` shapes raw beats into felt time.

## API Reference

### TempoMap

```python
from slackwater_tempo import TempoMap, TimeSignature, TransitionCurve

TempoMap(
    bpm: float = 120.0,
    time_signature: TimeSignature | None = None,
)
```

The core tempo engine. Tracks current BPM, manages smooth transitions, schedules beat callbacks. Does NOT own a thread — the caller pumps `update()` each frame.

| Property | Type | Description |
|---|---|---|
| `bpm` | `float` | Instantaneous BPM (interpolated during transitions) |
| `base_bpm` | `float` | Target BPM (where we're heading or settled) |
| `time_signature` | `TimeSignature` | Current time signature |
| `beat` | `int` | Total beats since start |
| `bar` | `int` | Current bar number (0-indexed) |
| `beat_in_bar` | `int` | Beat within current bar (0-indexed) |
| `is_transitioning` | `bool` | True if a tempo transition is in progress |
| `seconds_per_beat` | `float` | Duration of one beat in seconds |

**Methods:**

```python
tempo.set_bpm(
    target: float,
    *,
    transition_time: float = 0.0,
    curve: TransitionCurve = TransitionCurve.SIGMOID,
) -> None
```

Set a new target BPM. If `transition_time` > 0, the change is smooth (accelerando or ritardando). Default curve is `SIGMOID` — the shape of a musician settling into a new tempo.

```python
tempo.accelerando(target: float, duration: float = 4.0) -> None
tempo.ritardando(target: float, duration: float = 4.0) -> None
```

Directional convenience methods. `accelerando` requires `target > current bpm`. `ritardando` requires `target < current bpm`.

```python
tempo.update(now: float) -> None
```

Advance the tempo map. Call every frame with `time.monotonic()`.

```python
tempo.beat_phase() -> float
```

Where we are in the current beat, `0.0` → `1.0`.

**Callback registration:**

```python
tempo.on_beat(fn: Callable[[int, float], None], *, period: int = 1) -> BeatCallback
tempo.after_beat(fn: Callable[[int, float], None], *, offset: float = 0.05) -> BeatCallback
tempo.between_beats(fn: Callable[[int, float], None], *, count: int = 1) -> BeatCallback
```

- `on_beat`: fires on each beat (or every `period` beats). `fn` receives `(beat_number, timestamp)`.
- `after_beat`: fires `offset` seconds after each beat (for echoes, reactions).
- `between_beats`: fires `count` times evenly spaced between beats (subdivisions). `count=1` = eighth notes, `count=3` = sixteenths.

### TransitionCurve

```python
class TransitionCurve(Enum):
    LINEAR    # Metronome changing speed
    EASE      # Cosine ease-in-out (gentle)
    SIGMOID   # Smooth S-curve via tanh (default — most human)
```

### TimeSignature

```python
@dataclass(frozen=True)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4
```

Denominator must be a power of 2. `beats_per_bar` property returns `numerator`.

### BeatCallback

```python
@dataclass
class BeatCallback:
    on_beat: Callable[[int, float], None] | None = None
    after_beat: Callable[[int, float], None] | None = None
    between_beats: Callable[[int, float], None] | None = None
    period: int = 1
    offset: float = 0.0
    subdivision_count: int = 0
```

### GrooveEngine

```python
from slackwater_tempo import GrooveEngine, GameState, TempoPreset

GrooveEngine(
    swing: float = 0.0,          # 0.0 = straight, 1.0 = full swing
    push_drag_ms: float = 0.0,   # Negative = ahead, positive = behind
    humanize_ms: float = 0.0,    # Random timing variation
)
```

Shapes raw beats into felt time. Swing delays off-beats. Push/drag shifts everything ahead of or behind the grid. Humanization adds per-event variation.

**Methods:**

```python
groove.timing_offset(beat_in_bar: int = 0, is_off_beat: bool = False) -> float
```

Returns total timing offset in seconds for one event. Combines swing, push/drag, and humanization. Add to scheduled beat time to get the felt time.

```python
groove.apply_preset(state: GameState, tempo: TempoMap, *, transition_time: float = 4.0) -> TempoPreset
groove.apply_agent_groove(agent_name: str) -> None
groove.is_in_the_pocket() -> bool
```

**Musical Terminology Table:**

| GameState | Italian Marking | BPM | Character |
|---|---|---|---|
| `CALM` | Adagio | 66 | Slow, expressive, contemplative |
| `STEADY` | Andante | 92 | Walking pace, steady progress |
| `ACTIVE` | Allegro | 132 | Fast, lively, engaged |
| `URGENT` | Presto | 168 | Very fast, urgent, chaotic |

**Agent Grooves:**

| Agent | Swing | Push/Drag | Character |
|---|---|---|---|
| `lucineer` | 0.55 | +4.0ms | Deliberate, weighty, behind the beat |
| `earl` | 0.50 | −3.0ms | Eager, quick, ahead of the beat |
| `player` | 0.00 | 0.0ms | The reference grid |

### EnergyAdapter

```python
from slackwater_tempo import EnergyAdapter, PlayerBehavior, ActivityLevel

EnergyAdapter(
    tempo: TempoMap,
    smoothing_seconds: float = 7.0,
    min_bpm: float = 50.0,
    max_bpm: float = 180.0,
)
```

Observes player behavior and maps it to BPM via a smoothed energy score. Uses exponential moving average with configurable time constant. BPM mapping follows `min + (max - min) * energy^0.8`.

**Activity Level → BPM Mapping:**

| ActivityLevel | Dynamic | BPM | Italian |
|---|---|---|---|
| `IDLE` | pp | 60 | Largo |
| `RELAXED` | p | 72 | Adagio |
| `MODERATE` | mp | 92 | Andante |
| `ENGAGED` | mf | 120 | Moderato-Allegro |
| `INTENSE` | f | 144 | Allegro |
| `FRANTIC` | ff | 172 | Presto |

### BeatClock

```python
from slackwater_tempo import BeatClock

BeatClock(
    bpm: float = 120.0,
    time_signature: TimeSignature | None = None,
    tempo_map: TempoMap | None = None,
)
```

The shared synchronizing clock. Wraps a `TempoMap` and provides convenience methods: `tick()`, `pause()`, `resume()`, `is_downbeat()`, `next_downbeat()`, `beats_away(target_beat)`.

## Examples

### Basic tempo with smooth transition

```python
from slackwater_tempo import TempoMap
import time

tempo = TempoMap(bpm=72)
tempo.accelerando(120, duration=4.0)  # 4-second accelerando

now = time.monotonic()
while True:
    tempo.update(now)
    now = time.monotonic()
    if not tempo.is_transitioning:
        break
```

### Beat callbacks

```python
from slackwater_tempo import TempoMap

tempo = TempoMap(bpm=120)
tempo.on_beat(lambda beat, t: print(f"beat {beat}"))
tempo.between_beats(lambda beat, t: print(f"  sub"), count=1)  # eighths
```

### Full pipeline: energy → tempo → groove

```python
from slackwater_tempo import BeatClock, GrooveEngine, EnergyAdapter, PlayerBehavior, GameState

clock = BeatClock(bpm=72)
groove = GrooveEngine(swing=0.55, push_drag_ms=2.0)
groove.apply_preset(GameState.STEADY, clock.tempo_map, transition_time=2.0)

adapter = EnergyAdapter(clock.tempo_map, smoothing_seconds=5.0)

# Each frame:
adapter.observe(PlayerBehavior(build_rate=60, action_rate=30, chat_frequency=5))
adapter.update(time.monotonic())
clock.tick(time.monotonic())

offset = groove.timing_offset(beat_in_bar=clock.beat_in_bar())
# Add offset to scheduled event times for felt timing
```

## License

MIT
