# Module writer

Handwriting for robot arms. Give it a string and it draws it with a pen, using
single-stroke [Hershey fonts](https://en.wikipedia.org/wiki/Hershey_fonts) mapped onto a
page plane you teach by jogging the arm to three points.

## Models

This module provides the following model(s):

- [`chess-piece-detection:writer:writer-coordinator`](chess-piece-detection_writer_writer-coordinator.md) — writes text with an arm-mounted pen

## Quick start

```json
{
  "arm": "arm-1",
  "paper_origin": [300.0, -100.0, 50.0],
  "paper_x_point": [500.0, -100.0, 50.0],
  "paper_y_point": [300.0, 100.0, 50.0],
  "z_press_mm": -2.0
}
```

```json
{"write": {"text": "Hello, Viam!", "cap_height_mm": 12}}
```

See the [model docs](chess-piece-detection_writer_writer-coordinator.md) for calibration,
the full attribute list, and the `preview` / `calibrate` / `fonts` / `stop` commands.
