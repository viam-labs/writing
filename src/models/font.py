"""Turn text into 2D pen strokes using Hershey single-stroke fonts.

Hershey fonts are skeleton fonts: each glyph is a set of centerlines rather than
a filled outline, which is exactly what a pen needs. Tracing a TTF/OTF outline
instead would draw bubble letters.

Everything in this module works in millimetres on a flat page, with the origin
at the left end of the first line's baseline, +x to the right and +y up.
Mapping that page onto the robot's workspace is `geometry.PaperFrame`'s job.
"""

from typing import Iterable, List, Sequence, Tuple

from HersheyFonts import HersheyFonts

Point = Tuple[float, float]
Polyline = List[Point]

# Fonts that read well with a pen, deduplicated: the Hershey set ships several
# aliases (futural == rowmans, futuram == rowmand, rowmant == timesrb,
# scripts == cursive), so only one of each pair is listed here. The full set is
# HersheyFonts().default_font_names.
RECOMMENDED_FONTS = {
    "futural": "single-stroke sans; fewest waypoints, so the fastest to draw",
    "futuram": "heavier sans, drawn with doubled strokes",
    "timesr": "serif roman",
    "timesi": "serif italic",
    "scripts": "joined-up cursive; very few pen lifts, most handwriting-like",
    "gothiceng": "blackletter; slow, lots of strokes",
}

DEFAULT_FONT = "futural"


def available_fonts() -> List[str]:
    return list(HersheyFonts().default_font_names)


def render_text(
    text: str,
    cap_height_mm: float,
    font_name: str = DEFAULT_FONT,
    line_spacing: float = 1.2,
    simplify_tolerance_mm: float = 0.2,
) -> List[Polyline]:
    """Render `text` as a list of polylines.

    The pen stays down for the length of a polyline and lifts between them.
    Newlines start a new line of text; the library does not handle them itself,
    so each line is rendered separately and offset downwards.

    Args:
        cap_height_mm: height of a capital letter, e.g. 15.0
        line_spacing: line advance as a multiple of the font's full height
            (cap line to descender bottom), so 1.0 has descenders just touching
            the next line's capitals.
        simplify_tolerance_mm: Ramer-Douglas-Peucker tolerance. Every retained
            point costs a motion plan, so this matters more than it looks.
    """
    if cap_height_mm <= 0:
        raise ValueError("cap_height_mm must be positive")

    font = HersheyFonts()
    try:
        font.load_default_font(font_name)
    except Exception as exc:  # the library raises a bare Exception on unknown names
        raise ValueError(
            f"unknown font {font_name!r}; available: {', '.join(available_fonts())}"
        ) from exc

    # `normalize_rendering(f)` scales the font so its *full* height (cap line to
    # descender bottom) is f. We want to size by cap height instead, so work out
    # the ratio from the font's raw metrics and pre-divide.
    cap_line = font.render_options["cap_line"]
    base_line = font.render_options["base_line"]
    bottom_line = font.render_options["bottom_line"]
    full_span = bottom_line - cap_line
    baseline_frac = (bottom_line - base_line) / full_span  # baseline height / full height
    cap_frac = 1.0 - baseline_frac

    full_height_mm = cap_height_mm / cap_frac
    font.normalize_rendering(full_height_mm)

    # After normalising, y=0 sits at the descender bottom. Shift so y=0 is the baseline.
    baseline_offset = baseline_frac * full_height_mm
    line_advance = full_height_mm * line_spacing

    polylines: List[Polyline] = []
    for line_index, line in enumerate(text.split("\n")):
        if not line.strip():
            continue
        y_shift = -baseline_offset - line_index * line_advance
        for stroke in font.strokes_for_text(line):
            pts = [(float(x), float(y) + y_shift) for x, y in stroke]
            pts = _dedupe(pts)
            if len(pts) < 2:
                continue
            polylines.append(simplify(pts, simplify_tolerance_mm))

    return polylines


def bounds(polylines: Sequence[Polyline]) -> Tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over every point. Raises on empty input."""
    xs = [p[0] for poly in polylines for p in poly]
    ys = [p[1] for poly in polylines for p in poly]
    if not xs:
        raise ValueError("no strokes to measure")
    return min(xs), min(ys), max(xs), max(ys)


def translate(polylines: Sequence[Polyline], dx: float, dy: float) -> List[Polyline]:
    return [[(x + dx, y + dy) for x, y in poly] for poly in polylines]


def fit_width(polylines: Sequence[Polyline], max_width_mm: float) -> List[Polyline]:
    """Scale down uniformly about the page origin if the text is too wide.

    Leaves the strokes untouched when they already fit.
    """
    min_x, _, max_x, _ = bounds(polylines)
    width = max_x - min_x
    if width <= max_width_mm or width == 0:
        return [list(poly) for poly in polylines]
    k = max_width_mm / width
    return [[(x * k, y * k) for x, y in poly] for poly in polylines]


def point_count(polylines: Iterable[Polyline]) -> int:
    return sum(len(poly) for poly in polylines)


def simplify(points: Sequence[Point], tolerance_mm: float) -> Polyline:
    """Ramer-Douglas-Peucker. Drops points that sit within `tolerance_mm` of the
    chord they'd otherwise interrupt."""
    if tolerance_mm <= 0 or len(points) < 3:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        worst_dist, worst_i = -1.0, start
        for i in range(start + 1, end):
            d = _point_line_distance(points[i], points[start], points[end])
            if d > worst_dist:
                worst_dist, worst_i = d, i
        if worst_dist > tolerance_mm:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))

    return [p for p, k in zip(points, keep) if k]


def _point_line_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    # perpendicular distance to the infinite line through a and b
    return abs(dy * px - dx * py + bx * ay - by * ax) / seg_len_sq**0.5


def _dedupe(points: Sequence[Point], eps: float = 1e-9) -> Polyline:
    out: Polyline = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    return out
