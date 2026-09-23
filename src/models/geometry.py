"""Map 2D page coordinates onto the robot's 3D workspace.

A `PaperFrame` is built from three taught points: the page origin, a point out
along the page's +x direction, and any point on the +y side. That's enough to
build an orthonormal basis for the page plane, including its normal.

Pure Python 3-vector maths - no numpy, which keeps the PyInstaller bundle small.
"""

import math
from typing import List, Sequence, Tuple

from viam.proto.common import Pose

Vec3 = Tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3) -> Vec3:
    n = _norm(a)
    if n < 1e-9:
        raise ValueError("cannot normalise a zero-length vector")
    return _scale(a, 1.0 / n)


def as_vec3(value: Sequence[float], name: str) -> Vec3:
    seq = list(value)
    if len(seq) != 3:
        raise ValueError(f"{name} must be [x, y, z] in mm, got {seq!r}")
    return (float(seq[0]), float(seq[1]), float(seq[2]))


class PaperFrame:
    """The page plane, expressed in the robot's reference frame (mm)."""

    def __init__(
        self,
        origin: Vec3,
        x_point: Vec3,
        y_point: Vec3,
        pen_theta_degs: float = 0.0,
        flip_pen_axis: bool = False,
    ):
        self.origin = origin
        self.ex = _unit(_sub(x_point, origin))

        # Gram-Schmidt: strip the +x component off the y direction so the basis
        # is orthonormal even when the taught y point isn't perfectly square.
        t = _sub(y_point, origin)
        rejection = _sub(t, _scale(self.ex, _dot(t, self.ex)))
        if _norm(rejection) < 1e-6:
            raise ValueError(
                "paper_y_point is colinear with paper_origin -> paper_x_point; "
                "teach a point genuinely off that axis"
            )
        self.ey = _unit(rejection)
        self.ez = _cross(self.ex, self.ey)  # page normal, away from the paper

        self.pen_theta_degs = pen_theta_degs
        # The tool points into the page, i.e. along -ez, unless the arm's tool
        # frame is defined the other way round.
        self.pen_axis = self.ez if flip_pen_axis else _scale(self.ez, -1.0)

    def to_world(self, x: float, y: float, z: float = 0.0) -> Vec3:
        """Page (x, y) plus `z` mm along the page normal -> robot coordinates.

        Positive z is off the paper towards the pen, negative presses in.
        """
        return _add(
            self.origin,
            _add(_add(_scale(self.ex, x), _scale(self.ey, y)), _scale(self.ez, z)),
        )

    def pose(self, x: float, y: float, z: float = 0.0) -> Pose:
        wx, wy, wz = self.to_world(x, y, z)
        return Pose(
            x=wx,
            y=wy,
            z=wz,
            o_x=self.pen_axis[0],
            o_y=self.pen_axis[1],
            o_z=self.pen_axis[2],
            theta=self.pen_theta_degs,
        )

    def squareness_error_degs(self, y_point: Vec3) -> float:
        """How far off 90 degrees the taught x and y directions were.

        Large values mean the calibration points were sloppy and text will come
        out sheared relative to the page edges (the strokes themselves stay
        square, since the basis is orthonormalised).
        """
        raw_y = _unit(_sub(y_point, self.origin))
        cos = max(-1.0, min(1.0, _dot(self.ex, raw_y)))
        return abs(90.0 - math.degrees(math.acos(cos)))

    def describe(self) -> dict:
        return {
            "origin": list(self.origin),
            "x_axis": list(self.ex),
            "y_axis": list(self.ey),
            "normal": list(self.ez),
            "pen_axis": list(self.pen_axis),
            "pen_theta_degs": self.pen_theta_degs,
        }


def reach_violations(
    poses: Sequence[Pose], max_reach_mm: float, base: Vec3 = (0.0, 0.0, 0.0)
) -> List[dict]:
    """Points further from `base` than the arm can reach.

    A cheap sanity check, not real inverse kinematics: it catches "the paper is
    across the room" before the arm starts moving, but a point inside the sphere
    can still be unreachable in practice.
    """
    out = []
    for i, p in enumerate(poses):
        d = _norm(_sub((p.x, p.y, p.z), base))
        if d > max_reach_mm:
            out.append({"index": i, "distance_mm": round(d, 2), "pose": pose_to_dict(p)})
    return out


def pose_to_dict(p: Pose) -> dict:
    return {
        "x": round(p.x, 3),
        "y": round(p.y, 3),
        "z": round(p.z, 3),
        "o_x": round(p.o_x, 4),
        "o_y": round(p.o_y, 4),
        "o_z": round(p.o_z, 4),
        "theta": round(p.theta, 3),
    }
