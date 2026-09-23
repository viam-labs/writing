# Model chess-piece-detection:writer:writer-coordinator

Makes a robot arm write text with a pen.

Text is rendered with [Hershey fonts](https://en.wikipedia.org/wiki/Hershey_fonts) —
single-stroke vector fonts where each glyph is a set of centrelines rather than a filled
outline. Tracing a TTF/OTF outline instead would draw bubble letters. The resulting 2D
strokes are mapped onto a page plane in the arm's workspace, taught from three points,
and drawn with the pen lifting between strokes.

## Configuration

```json
{
  "arm": "arm-1",
  "motion_service": "builtin",
  "paper_origin": [300.0, -100.0, 50.0],
  "paper_x_point": [500.0, -100.0, 50.0],
  "paper_y_point": [300.0, 100.0, 50.0],
  "cap_height_mm": 15.0,
  "z_lift_mm": 15.0,
  "z_press_mm": -2.0,
  "font": "futural"
}
```

### Attributes

| Name | Type | Inclusion | Default | Description |
|---|---|---|---|---|
| `arm` | string | Required | — | Name of the arm holding the pen |
| `paper_origin` | [float] | Required | — | `[x, y, z]` mm of the page origin — where text at `(0, 0)` lands |
| `paper_x_point` | [float] | Required | — | Any point out along the page's +x direction |
| `paper_y_point` | [float] | Required | — | Any point on the page's +y side |
| `motion_service` | string | Optional | — | Motion service name. When set, pen-down segments are planned as straight lines |
| `reference_frame` | string | Optional | `"world"` | Frame the paper points are given in. Motion-service mode only |
| `cap_height_mm` | float | Optional | `15.0` | Height of a capital letter |
| `line_spacing` | float | Optional | `1.2` | Line advance, as a multiple of the font's full height |
| `font` | string | Optional | `"futural"` | Hershey font name. Run the `fonts` command to list them |
| `z_lift_mm` | float | Optional | `15.0` | Pen-up height above the page, along the page normal |
| `z_press_mm` | float | Optional | `0.0` | Pen-down height. Negative presses into the page |
| `simplify_tolerance_mm` | float | Optional | `0.2` | Waypoint thinning tolerance. Higher is faster and coarser |
| `pen_theta_degs` | float | Optional | `0.0` | Rotation of the tool about the pen axis |
| `flip_pen_axis` | bool | Optional | `false` | Set if the tool frame points out of the page rather than into it |
| `max_reach_mm` | float | Optional | — | Pre-flight sanity check: refuse to write if any waypoint is further than this from the arm base |
| `line_tolerance_mm` | float | Optional | `1.0` | Linear-constraint tolerance. Motion-service mode only |
| `orientation_tolerance_degs` | float | Optional | `5.0` | Linear-constraint tolerance. Motion-service mode only |
| `move_timeout_s` | float | Optional | `20.0` | Per-waypoint move timeout |

The paper points do not need to be perfectly square: the +y direction is orthogonalised
against +x. A skew over 3° logs a warning, since it means the text will sit at an angle
relative to the page edges.

Which frame the points are in depends on the mode. Without `motion_service`, moves go
through `arm.move_to_position`, so the points are in the **arm's own base frame**. With
`motion_service` set, they are in `reference_frame` (`"world"` by default).

## DoCommand

### `calibrate`

Reads the arm's current tip pose. Jog the pen to each of the three page points in turn
and run this to read off the numbers.

```json
{"calibrate": {}}
```

```json
{"calibrate": {"point": [300.12, -99.87, 50.4], "current_pose": {...}, "configured_paper": {...}}}
```

### `preview`

Plans the strokes without moving. Use this while calibrating.

```json
{"preview": {"text": "hello\nviam", "x": 20, "y": -20, "max_poses": 5}}
```

```json
{"preview": {
  "strokes": 15,
  "points": 89,
  "bounds_mm": {"min_x": 21.14, "min_y": -39.2, "max_x": 59.43, "max_y": -8.0, "width": 38.29, "height": 31.2},
  "reach_check": {"checked": true, "max_reach_mm": 900.0, "violations": [], "violation_count": 0},
  "poses": [{"x": 322.286, "y": -108.0, "z": 48.0, "o_x": 0.0, "o_y": 0.0, "o_z": -1.0, "theta": 0.0}]
}}
```

### `write`

Draws the text. Blocks until finished. Every configured default can be overridden per
call.

```json
{"write": {"text": "Hello, Viam!", "x": 10, "y": -20, "cap_height_mm": 12, "font": "scripts", "max_width_mm": 180}}
```

| Arg | Description |
|---|---|
| `text` | Required. `\n` starts a new line |
| `x`, `y` | Page position of the first line's baseline start, mm. Default `0, 0` |
| `cap_height_mm`, `font`, `line_spacing`, `simplify_tolerance_mm`, `z_lift_mm`, `z_press_mm` | Override the configured value for this call |
| `max_width_mm` | Scale the whole block down if it comes out wider than this |

Returns the same fields as `preview`, plus `strokes_drawn` and `stopped_early`.

### `fonts`

Lists every available Hershey font, and a curated subset with notes.

```json
{"fonts": {}}
```

### `stop`

Halts the arm and aborts an in-progress `write`.

```json
{"stop": {}}
```

## Getting it working

1. Mount the pen in a **spring-loaded holder** with a few mm of travel. Paper isn't flat,
   the taught plane isn't exact, and the arm has backlash — compliance absorbs all three
   and you stop needing sub-millimetre Z accuracy. Set `z_press_mm` a couple of mm
   *below* the page so the spring stays loaded across the whole sheet.
2. Jog the pen to the page origin, run `calibrate`, and note the `point`. Repeat along
   the page's +x edge and its +y side. Paste all three into the config.
3. Run `preview` and check `bounds_mm` lands inside your sheet.
4. Run `write` with a short string and a small `cap_height_mm` first.

Every waypoint is a separate motion plan, so drawing speed is dominated by point count —
`preview` reports it. If writing is too slow, raise `simplify_tolerance_mm`, or pick
`futural` (fewest strokes) or `scripts` (cursive, so very few pen lifts).
