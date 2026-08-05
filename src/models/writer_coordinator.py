import asyncio
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple

from viam.components.arm import Arm
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Pose, PoseInFrame, ResourceName
from viam.proto.service.motion import Constraints, LinearConstraint
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.services.generic import Generic
from viam.services.motion import MotionClient
from viam.utils import ValueTypes, struct_to_dict

from . import font, geometry

DEFAULTS = {
    "z_lift_mm": 15.0,
    "z_press_mm": 0.0,
    "font": font.DEFAULT_FONT,
    "cap_height_mm": 15.0,
    "line_spacing": 1.2,
    "simplify_tolerance_mm": 0.2,
    "pen_theta_degs": 0.0,
    "flip_pen_axis": False,
    "reference_frame": "world",
    "line_tolerance_mm": 1.0,
    "orientation_tolerance_degs": 5.0,
    "move_timeout_s": 20.0,
}


class WriterCoordinator(Generic, EasyResource):
    # To enable debug-level logging, either run viam-server with the --debug option,
    # or configure your resource/machine to display debug logs.
    MODEL: ClassVar[Model] = Model(
        ModelFamily("chess-piece-detection", "writer"), "writer-coordinator"
    )

    arm: Arm
    motion: Optional[MotionClient]
    paper: geometry.PaperFrame

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        settings = cls._parse_config(config)
        deps = [Arm.get_resource_name(settings["arm"]).name]
        if settings["motion_service"]:
            deps.append(MotionClient.get_resource_name(settings["motion_service"]).name)
        return deps, []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> None:
        settings = self._parse_config(config)
        self.settings = settings

        self.arm_name = settings["arm"]
        self.arm = dependencies[Arm.get_resource_name(self.arm_name)]

        self.motion = None
        if settings["motion_service"]:
            self.motion = dependencies[
                MotionClient.get_resource_name(settings["motion_service"])
            ]

        self.paper = geometry.PaperFrame(
            origin=settings["paper_origin"],
            x_point=settings["paper_x_point"],
            y_point=settings["paper_y_point"],
            pen_theta_degs=settings["pen_theta_degs"],
            flip_pen_axis=settings["flip_pen_axis"],
        )

        self._write_lock = asyncio.Lock()
        self._stop_requested = False

        skew = self.paper.squareness_error_degs(settings["paper_y_point"])
        if skew > 3.0:
            self.logger.warning(
                "taught paper x and y directions are %.1f degrees off square; "
                "text will be placed relative to a squared-up frame",
                skew,
            )
        self.logger.info(
            "paper frame ready: origin=%s normal=%s mode=%s",
            [round(v, 1) for v in self.paper.origin],
            [round(v, 3) for v in self.paper.ez],
            "motion service (linear)" if self.motion else "arm.move_to_position",
        )

    # ---------------------------------------------------------------- config

    @classmethod
    def _parse_config(cls, config: ComponentConfig) -> Dict[str, Any]:
        """Validate and normalise attributes. Raises ValueError on bad config."""
        attrs = struct_to_dict(config.attributes)

        arm_name = attrs.get("arm")
        if not arm_name or not isinstance(arm_name, str):
            raise ValueError('"arm" is required and must be the name of an arm')

        settings: Dict[str, Any] = {
            "arm": arm_name,
            "motion_service": attrs.get("motion_service") or None,
        }

        for key in ("paper_origin", "paper_x_point", "paper_y_point"):
            if key not in attrs:
                raise ValueError(
                    f'"{key}" is required; jog the pen to each point and use the '
                    '"calibrate" command to read the values off the arm'
                )
            settings[key] = geometry.as_vec3(attrs[key], key)

        for key, default in DEFAULTS.items():
            value = attrs.get(key, default)
            if isinstance(default, bool):
                settings[key] = bool(value)
            elif isinstance(default, float):
                settings[key] = float(value)
            else:
                settings[key] = str(value)

        if settings["font"] not in font.available_fonts():
            raise ValueError(
                f'unknown font {settings["font"]!r}; try one of: '
                + ", ".join(font.RECOMMENDED_FONTS)
            )
        if settings["cap_height_mm"] <= 0:
            raise ValueError('"cap_height_mm" must be positive')
        if settings["z_lift_mm"] <= settings["z_press_mm"]:
            raise ValueError('"z_lift_mm" must be greater than "z_press_mm"')

        max_reach = attrs.get("max_reach_mm")
        settings["max_reach_mm"] = float(max_reach) if max_reach else None

        # Building the frame here means bad calibration points are rejected at
        # config time rather than on the first write.
        geometry.PaperFrame(
            settings["paper_origin"],
            settings["paper_x_point"],
            settings["paper_y_point"],
        )
        return settings

    # ------------------------------------------------------------- commands

    async def do_command(
        self,
        command: Mapping[str, ValueTypes],
        *,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Mapping[str, ValueTypes]:
        result: Dict[str, Any] = {}
        for name, raw_args in command.items():
            args = raw_args if isinstance(raw_args, dict) else {}
            if name == "write":
                result[name] = await self._do_write(args)
            elif name == "preview":
                result[name] = self._do_preview(args)
            elif name == "calibrate":
                result[name] = await self._do_calibrate()
            elif name == "fonts":
                result[name] = {
                    "available": font.available_fonts(),
                    "recommended": dict(font.RECOMMENDED_FONTS),
                }
            elif name == "stop":
                self._stop_requested = True
                await self.arm.stop()
                result[name] = {"stopped": True}
            else:
                raise ValueError(
                    f"unknown command {name!r}; expected one of: "
                    "write, preview, calibrate, fonts, stop"
                )
        return result

    async def get_status(
        self, *, timeout: Optional[float] = None, **kwargs
    ) -> Mapping[str, ValueTypes]:
        return {
            "writing": self._write_lock.locked(),
            "arm": self.arm_name,
            "linear_moves": self.motion is not None,
            "paper": self.paper.describe(),
            "font": self.settings["font"],
            "cap_height_mm": self.settings["cap_height_mm"],
        }

    def _plan(
        self, args: Mapping[str, Any]
    ) -> Tuple[List[font.Polyline], Dict[str, Any]]:
        """Text -> page-space polylines, with sizing and placement applied."""
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError('"text" is required and must be a non-empty string')

        s = self.settings
        polylines = font.render_text(
            text,
            cap_height_mm=float(args.get("cap_height_mm", s["cap_height_mm"])),
            font_name=str(args.get("font", s["font"])),
            line_spacing=float(args.get("line_spacing", s["line_spacing"])),
            simplify_tolerance_mm=float(
                args.get("simplify_tolerance_mm", s["simplify_tolerance_mm"])
            ),
        )
        if not polylines:
            raise ValueError(f"{text!r} produced no strokes in this font")

        max_width = args.get("max_width_mm")
        if max_width:
            polylines = font.fit_width(polylines, float(max_width))

        polylines = font.translate(
            polylines, float(args.get("x", 0.0)), float(args.get("y", 0.0))
        )

        min_x, min_y, max_x, max_y = font.bounds(polylines)
        info: Dict[str, Any] = {
            "strokes": len(polylines),
            "points": font.point_count(polylines),
            "bounds_mm": {
                "min_x": round(min_x, 2),
                "min_y": round(min_y, 2),
                "max_x": round(max_x, 2),
                "max_y": round(max_y, 2),
                "width": round(max_x - min_x, 2),
                "height": round(max_y - min_y, 2),
            },
        }
        return polylines, info

    def _do_preview(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        polylines, info = self._plan(args)
        poses = [
            self.paper.pose(x, y, self.settings["z_press_mm"])
            for poly in polylines
            for x, y in poly
        ]
        info["reach_check"] = self._reach_check(poses)
        limit = int(args.get("max_poses", 0))
        if limit:
            info["poses"] = [geometry.pose_to_dict(p) for p in poses[:limit]]
        return info

    async def _do_write(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        polylines, info = self._plan(args)
        z_lift = float(args.get("z_lift_mm", self.settings["z_lift_mm"]))
        z_press = float(args.get("z_press_mm", self.settings["z_press_mm"]))
        if z_lift <= z_press:
            raise ValueError("z_lift_mm must be greater than z_press_mm")

        all_poses = [
            self.paper.pose(x, y, z)
            for poly in polylines
            for x, y in poly
            for z in (z_press, z_lift)
        ]
        check = self._reach_check(all_poses)
        info["reach_check"] = check
        if check.get("violation_count"):
            raise ValueError(
                f"{check['violation_count']} of {len(all_poses)} waypoints sit beyond "
                "max_reach_mm; move the paper closer or shrink the text"
            )

        if self._write_lock.locked():
            raise RuntimeError("a write is already in progress")

        strokes_done = 0
        pen_down_at: Optional[Tuple[float, float]] = None
        async with self._write_lock:
            self._stop_requested = False
            try:
                for poly in polylines:
                    if self._stop_requested:
                        break
                    start_x, start_y = poly[0]
                    # Travel above the start of the stroke, then drop the pen.
                    await self._goto(
                        self.paper.pose(start_x, start_y, z_lift), linear=False
                    )
                    pen_down_at = (start_x, start_y)
                    await self._goto(
                        self.paper.pose(start_x, start_y, z_press), linear=True
                    )
                    for x, y in poly[1:]:
                        if self._stop_requested:
                            break
                        await self._goto(self.paper.pose(x, y, z_press), linear=True)
                        pen_down_at = (x, y)
                    await self._goto(
                        self.paper.pose(*pen_down_at, z_lift), linear=True
                    )
                    pen_down_at = None
                    strokes_done += 1
                    self.logger.debug("stroke %d/%d done", strokes_done, len(polylines))
            finally:
                # A stop or a failed move can leave the pen resting on the paper.
                # Lift straight up from where it actually is rather than towards
                # the end of the stroke, which would drag a line across the page.
                if pen_down_at is not None:
                    try:
                        await self._goto(
                            self.paper.pose(*pen_down_at, z_lift), linear=True
                        )
                    except Exception:
                        self.logger.warning(
                            "could not lift the pen off the paper", exc_info=True
                        )

        info["strokes_drawn"] = strokes_done
        info["stopped_early"] = self._stop_requested
        return info

    async def _do_calibrate(self) -> Dict[str, Any]:
        """Read the arm's current tip pose, for teaching the three paper points."""
        pose = await self.arm.get_end_position()
        return {
            "current_pose": geometry.pose_to_dict(pose),
            "point": [round(pose.x, 2), round(pose.y, 2), round(pose.z, 2)],
            "hint": (
                "Jog the pen tip to the page origin, then out along the page's +x "
                "direction, then to a point up its +y direction, running this command "
                "at each. Paste the three `point` values into paper_origin, "
                "paper_x_point and paper_y_point."
            ),
            "configured_paper": self.paper.describe(),
        }

    # --------------------------------------------------------------- motion

    async def _goto(self, pose: Pose, linear: bool) -> None:
        """Move the pen tip to `pose`.

        Pen-down segments ask the motion service for a straight line so the tip
        tracks the stroke instead of arcing between waypoints. Pen-up travel
        doesn't care about the path, so it takes the cheaper direct move.
        """
        timeout = self.settings["move_timeout_s"]
        if self.motion and linear:
            ok = await self.motion.move(
                component_name=Arm.get_resource_name(self.arm_name),
                destination=PoseInFrame(
                    reference_frame=self.settings["reference_frame"], pose=pose
                ),
                constraints=Constraints(
                    linear_constraint=[
                        LinearConstraint(
                            line_tolerance_mm=self.settings["line_tolerance_mm"],
                            orientation_tolerance_degs=self.settings[
                                "orientation_tolerance_degs"
                            ],
                        )
                    ]
                ),
                timeout=timeout,
            )
            if not ok:
                raise RuntimeError(
                    "motion service could not plan a linear move to "
                    f"{geometry.pose_to_dict(pose)}"
                )
        else:
            await self.arm.move_to_position(pose, timeout=timeout)

    def _reach_check(self, poses: Sequence[Pose]) -> Dict[str, Any]:
        max_reach = self.settings["max_reach_mm"]
        if not max_reach:
            return {"checked": False, "reason": "max_reach_mm not configured"}
        violations = geometry.reach_violations(poses, max_reach)
        return {
            "checked": True,
            "max_reach_mm": max_reach,
            "violations": violations[:10],
            "violation_count": len(violations),
        }
