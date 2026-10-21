"""Look at the closest face in Reachy Mini's camera.

The agent uses ``media_backend="no_media"``, which releases the camera for this
module to open directly. A generated gesture's sustained head angle is filtered
out while a face is held, leaving quick motion, lean, and antennas layered over
the gaze target.
"""

from __future__ import annotations

import logging
import math
import platform
import threading
import time
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray
from reachy_animation.pose import Pose, to_target
from reachy_mini.media.camera_utils import intrinsics_for_size
from reachy_mini.utils.rotation import Rotation
from reachy_mini.vision.look_at import look_at_image_pose

if TYPE_CHECKING:
    from reachy_mini.media.camera_constants import CameraSpecs
    from reachy_mini.vision.face_detector import Face

logger = logging.getLogger("reachy-agent")

_PITCH_TRIM = math.radians(15.0)
_HOLD_S = 1.5
_LOCK_LOST_S = 1.5
_EASE_S = 0.8
_FACE_EASE_S = 0.45
_MAX_GAZE_SPEED = math.radians(25.0)
_MOTION_S = 0.4
_MIN_AREA = 0.003
_MAX_JUMP = 0.4
_TRACK_WIDTH = 320


def _area(face: Face) -> float:
    return face.bbox[2] * face.bbox[3]


def _center(face: Face, width: int, height: int) -> tuple[float, float]:
    return (
        face.nose[0] / max(width - 1, 1) * 2 - 1,
        face.nose[1] / max(height - 1, 1) * 2 - 1,
    )


def closest_face(
    faces: list[Face],
    held: tuple[float, float] | None,
    width: int,
    height: int,
) -> Face | None:
    """Acquire the largest face, then stay with the face nearest the lock."""
    min_area = _MIN_AREA * width * height
    faces = [face for face in faces if _area(face) >= min_area]
    if not faces:
        return None
    if held is None:
        return max(faces, key=_area)
    nearest = min(
        faces,
        key=lambda face: _dist2(_center(face, width, height), held),
    )
    if _dist2(_center(nearest, width, height), held) > _MAX_JUMP**2:
        return None
    return nearest


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def aim_euler(
    u: float,
    v: float,
    matrix: NDArray[np.float64],
    distortion: NDArray[np.float64],
    head: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Return the head orientation that looks at image pixel ``(u, v)``."""
    aimed = look_at_image_pose(u, v, matrix, distortion, head)
    euler = np.asarray(
        Rotation.from_matrix(aimed[:3, :3]).as_euler("xyz"),
        dtype=np.float64,
    )
    euler[1] += _PITCH_TRIM
    return euler


def _wrap(delta: NDArray[np.float64]) -> NDArray[np.float64]:
    return (delta + np.pi) % (2 * np.pi) - np.pi


def _wrap_angle(delta: float) -> float:
    return (delta + math.pi) % (2 * math.pi) - math.pi


class FaceGaze:
    """Run face detection in the background and aim each animator pose."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sight: (
            tuple[
                float,
                float,
                NDArray[np.float64],
                NDArray[np.float64],
                float,
            ]
            | None
        ) = None
        self._face_observation: tuple[float, float] | None = None
        self._gaze = np.zeros(3)
        self._target = np.zeros(3)
        self._computed_t = 0.0
        self._seen = 0.0
        self._head = np.eye(4)
        self._applied = 0.0
        self._tracking = False
        self._warned = False
        self._held_orient = np.zeros(3)
        self._held_body = 0.0
        self._held_ready = False
        self._follow = 0.0

    def start(self) -> None:
        """Start tracking, or log and return when no camera is present."""
        self._thread = threading.Thread(
            target=self._run,
            name="face-gaze",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def face_observation(self, max_age_s: float = 0.5) -> tuple[bool, float]:
        """Return whether a face is visible and its fraction of the image area."""
        with self._lock:
            observation = self._face_observation
        if observation is None or time.monotonic() - observation[1] > max_age_s:
            return False, 0.0
        return True, observation[0]

    def apply(
        self,
        pose: Pose,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
        """Aim this animation pose at the tracked face."""
        now = time.monotonic()
        dt = min(now - self._applied, 0.1) if self._applied else 1.0 / 60.0
        self._applied = now
        with self._lock:
            sight = self._sight
        if sight is not None and sight[4] > self._computed_t:
            self._computed_t = sight[4]
            self._seen = sight[4]
            try:
                self._target = aim_euler(
                    sight[0],
                    sight[1],
                    sight[2],
                    sight[3],
                    self._head,
                )
                if not self._tracking:
                    logger.info("gaze: looking at the closest face")
                    self._tracking = True
            except Exception:
                if not self._warned:
                    logger.warning(
                        "gaze: could not aim at the face",
                        exc_info=True,
                    )
                    self._warned = True
        elif self._seen and now - self._seen > _HOLD_S:
            self._target = np.zeros(3)
            if self._tracking and float(np.max(np.abs(self._gaze))) < math.radians(1.5):
                logger.info("gaze: face lost, back to the animation")
                self._tracking = False

        alpha = 1.0 - math.exp(-dt / _EASE_S)
        gaze_step = alpha * _wrap(self._target - self._gaze)
        max_step = _MAX_GAZE_SPEED * dt
        step_size = float(np.linalg.norm(gaze_step))
        if step_size > max_step:
            gaze_step *= max_step / step_size
        self._gaze = self._gaze + gaze_step

        euler = np.asarray(pose[3:6], dtype=np.float64)
        if not self._held_ready:
            self._held_orient = euler.copy()
            self._held_body = float(pose[8])
            self._held_ready = True
        settle = 1.0 - math.exp(-dt / _MOTION_S)
        self._held_orient = self._held_orient + settle * _wrap(
            euler - self._held_orient
        )
        self._held_body += settle * _wrap_angle(float(pose[8]) - self._held_body)
        quick = _wrap(euler - self._held_orient)
        quick_body = _wrap_angle(float(pose[8]) - self._held_body)
        want = 1.0 if self._seen and now - self._seen <= _HOLD_S else 0.0
        self._follow += alpha * (want - self._follow)

        aimed = pose.copy()
        aimed[3:6] = (1.0 - self._follow) * euler + self._follow * (self._gaze + quick)
        aimed[8] = (1.0 - self._follow) * float(pose[8]) + self._follow * quick_body
        head, antennas, body_yaw = to_target(aimed)
        self._head = head
        return head, antennas, body_yaw

    def _run(self) -> None:
        try:
            self._loop()
        except Exception:
            logger.exception("gaze: camera loop stopped")

    def _loop(self) -> None:
        found = _find_camera()
        if found is None:
            return
        path, specs = found

        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstApp", "1.0")
        from gi.repository import Gst
        from reachy_mini.vision.face_detector import FaceDetector

        Gst.init(None)
        opened = _open_camera(path, specs)
        if opened is None:
            logger.warning("gaze: could not open the camera at %s", path)
            return
        pipeline, sink, width, height = opened
        logger.info(
            "gaze: camera %s, tracking at %dx%d",
            specs.name,
            width,
            height,
        )
        crop = float(specs.default_resolution.value[3])
        distortion = np.asarray(specs.D, dtype=np.float64)
        matrix: NDArray[np.float64] | None = None
        held: tuple[float, float] | None = None
        smooth: NDArray[np.float64] | None = None
        smoothed_at = 0.0
        lost_since: float | None = None
        period = 1.0 / 12.0
        try:
            detector = FaceDetector()
            while not self._stop.is_set():
                started = time.monotonic()
                sample = sink.try_pull_sample(200 * Gst.MSECOND)
                if sample is None:
                    continue
                structure = sample.get_caps().get_structure(0)
                frame_w = int(structure.get_value("width"))
                frame_h = int(structure.get_value("height"))
                buf = sample.get_buffer()
                frame = np.frombuffer(
                    buf.extract_dup(0, buf.get_size()),
                    dtype=np.uint8,
                ).reshape((frame_h, frame_w, 3))
                if matrix is None or (frame_w, frame_h) != (width, height):
                    width, height = frame_w, frame_h
                    matrix = intrinsics_for_size(
                        specs.K,
                        crop,
                        (frame_w, frame_h),
                    )
                faces = detector.detect(frame)
                observed_at = time.monotonic()
                face = closest_face(
                    faces,
                    held,
                    frame_w,
                    frame_h,
                )
                if face is None and held is not None:
                    if lost_since is None:
                        lost_since = observed_at
                    elif observed_at - lost_since >= _LOCK_LOST_S:
                        logger.info("gaze: locked face lost; acquiring a new face")
                        held = None
                        smooth = None
                        smoothed_at = 0.0
                        lost_since = None
                        face = closest_face(
                            faces,
                            None,
                            frame_w,
                            frame_h,
                        )
                elif face is not None:
                    lost_since = None

                observed_face = face or (max(faces, key=_area) if faces else None)
                if (
                    observed_face is not None
                    and _area(observed_face) < _MIN_AREA * frame_w * frame_h
                ):
                    observed_face = None
                with self._lock:
                    self._face_observation = (
                        (
                            _area(observed_face) / (frame_w * frame_h),
                            observed_at,
                        )
                        if observed_face is not None
                        else None
                    )

                if face is None:
                    if held is None:
                        lost_since = None
                else:
                    held = _center(face, frame_w, frame_h)
                    nose = np.asarray(face.nose, dtype=np.float64)
                    if smooth is None:
                        smooth = nose
                    else:
                        smooth_dt = min(observed_at - smoothed_at, 0.1)
                        smooth_alpha = 1.0 - math.exp(-smooth_dt / _FACE_EASE_S)
                        smooth = smooth + smooth_alpha * (nose - smooth)
                    smoothed_at = observed_at
                    u = float(np.clip(smooth[0], 1.0, frame_w - 2))
                    v = float(np.clip(smooth[1], 1.0, frame_h - 2))
                    with self._lock:
                        self._sight = (
                            u,
                            v,
                            matrix,
                            distortion,
                            observed_at,
                        )
                remaining = period - (time.monotonic() - started)
                if remaining > 0:
                    self._stop.wait(remaining)
        finally:
            pipeline.set_state(Gst.State.NULL)


def _open_camera(
    path: str,
    specs: CameraSpecs,
) -> tuple[Any, Any, int, int] | None:
    """Start a BGR appsink on Reachy's camera."""
    import gi

    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    from gi.repository import GLib, Gst, GstApp  # noqa: F401

    width, height, fps, _crop = specs.default_resolution.value
    track_w = min(_TRACK_WIDTH, int(width))
    track_h = max(2, round(track_w * int(height) / int(width) / 2) * 2)
    tail = (
        "queue max-size-buffers=1 leaky=downstream ! videoscale ! "
        "videoconvert ! "
        f"video/x-raw,format=BGR,width={track_w},height={track_h} ! "
        "appsink name=gaze drop=true max-buffers=1 sync=false"
    )
    for description in _sources(
        path,
        int(width),
        int(height),
        int(fps),
        tail,
    ):
        try:
            pipeline = Gst.parse_launch(description)
        except GLib.Error as exc:
            logger.debug("gaze: camera pipeline rejected: %s", exc)
            continue
        sink = pipeline.get_by_name("gaze") if pipeline is not None else None
        if pipeline is None or sink is None:
            continue
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            continue
        _change, state, _pending = pipeline.get_state(5 * Gst.SECOND)
        if state == Gst.State.PLAYING:
            return pipeline, sink, track_w, track_h
        bus = pipeline.get_bus()
        message = (
            bus.timed_pop_filtered(0, Gst.MessageType.ERROR)
            if bus is not None
            else None
        )
        if message is not None:
            err, debug = message.parse_error()
            logger.debug("gaze: camera mode refused: %s (%s)", err, debug)
        pipeline.set_state(Gst.State.NULL)
    return None


_CAM_NAMES = ("Reachy", "Arducam_12MP", "imx708")


def _match_camera(
    names: list[str],
) -> tuple[int, str, CameraSpecs] | None:
    """Match a camera name using the same priority as the Reachy SDK."""
    from reachy_mini.media.camera_constants import (
        ArducamSpecs,
        ReachyMiniLiteCamSpecs,
    )

    for needle in _CAM_NAMES:
        for index, name in enumerate(names):
            if needle in name:
                specs = (
                    ArducamSpecs()
                    if needle == "Arducam_12MP"
                    else ReachyMiniLiteCamSpecs()
                )
                return index, name, specs
    return None


def _find_camera() -> tuple[str, CameraSpecs] | None:
    """Return Reachy's camera device and specs, if available."""
    if platform.system() == "Darwin":
        names = _darwin_camera_names()
        found = _match_camera(names)
        if found is None:
            seen = f" (saw: {', '.join(names)})" if names else ""
            logger.info(
                "gaze: no Reachy camera%s, the head stays with the animation",
                seen,
            )
            return None
        index, name, specs = found
        logger.info("gaze: using %s", name)
        return str(index), specs

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    from reachy_mini.media.device_detection import get_video_device

    Gst.init(None)
    path, specs = get_video_device()
    if not path or specs is None:
        logger.info("gaze: no Reachy camera, the head stays with the animation")
        return None
    return path, specs


def _darwin_camera_names() -> list[str]:
    """Return macOS video device names in AVFoundation order."""
    import objc

    devices = objc.lookUpClass("AVCaptureDevice").devicesWithMediaType_("vide")
    return [str(device.localizedName()) for device in devices or []]


def _sources(
    path: str,
    width: int,
    height: int,
    fps: int,
    tail: str,
) -> list[str]:
    """Build camera pipelines, trying the strict mode first."""
    system = platform.system()
    if system == "Darwin":
        src = f"avfvideosrc device-index={int(path)}"
        raw = f"video/x-raw,width={width},height={height}"
        return [
            f"{src} ! {raw},framerate={fps}/1 ! {tail}",
            f"{src} ! {raw} ! {tail}",
            f"{src} ! {tail}",
        ]
    if path == "imx708":
        raw = f"video/x-raw,width={width},height={height}"
        return [
            f"libcamerasrc ! {raw},framerate={fps}/1 ! {tail}",
            f"libcamerasrc ! {tail}",
        ]
    src = f"v4l2src device={path}"
    jpeg = f"image/jpeg,width={width},height={height}"
    return [
        f"{src} ! {jpeg},framerate={fps}/1 ! jpegdec ! {tail}",
        f"{src} ! jpegdec ! {tail}",
        f"{src} ! {tail}",
    ]
