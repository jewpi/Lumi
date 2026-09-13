"""Pure helpers for converting /map and /scan into web API payloads."""

import io
import math
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

UNKNOWN_GRAY = 127
FREE_WHITE = 255
OCCUPIED_BLACK = 0

SCAN_COLOR = (255, 64, 64)
ROBOT_COLOR = (32, 128, 255)
HEADING_COLOR = (0, 200, 96)


def quaternion_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """Return the planar yaw of a quaternion in radians."""
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def grid_to_array(data, height: int, width: int) -> np.ndarray:
    """Return the occupancy grid as (height, width) int8, row 0 at the top.

    ROS stores ``data[0]`` at the map origin, i.e. the bottom-left corner with
    y increasing upwards, so the reshaped grid is flipped to image order.
    """
    try:
        flat = np.frombuffer(data, dtype=np.int8)
    except (TypeError, BufferError):
        flat = np.asarray(data, dtype=np.int8)
    if flat.size != height * width:
        raise ValueError(f"grid has {flat.size} cells, expected {height}x{width}")
    return flat.reshape(height, width)[::-1]


def grid_to_rgb(grid: np.ndarray, occupied_threshold: int = 50) -> np.ndarray:
    """Return an RGB uint8 image: white free, black occupied, gray unknown."""
    gray = np.full(grid.shape, UNKNOWN_GRAY, dtype=np.uint8)
    gray[(grid >= 0) & (grid < occupied_threshold)] = FREE_WHITE
    gray[grid >= occupied_threshold] = OCCUPIED_BLACK
    return np.dstack([gray, gray, gray])


def scan_to_points(
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    max_points: int = 0,
) -> np.ndarray:
    """Return valid scan returns as (N, 2) sensor-frame metres.

    Invalid returns (0.0, inf, nan, out of range) are dropped. When
    ``max_points`` is positive the survivors are thinned evenly across the
    sweep so the silhouette is preserved instead of clipping one side.
    """
    values = np.asarray(ranges, dtype=np.float64)
    if values.size == 0:
        return np.empty((0, 2))
    angles = angle_min + np.arange(values.size) * angle_increment
    valid = np.isfinite(values) & (values >= range_min) & (values <= range_max)
    values, angles = values[valid], angles[valid]
    if max_points > 0 and values.size > max_points:
        picks = np.linspace(0, values.size - 1, max_points).astype(int)
        values, angles = values[picks], angles[picks]
    return np.column_stack([values * np.cos(angles), values * np.sin(angles)])


def scan_to_bins(
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    bins: int = 360,
    angle_offset: float = 0.0,
) -> List[Optional[float]]:
    """Return a fixed-length polar array: index 0 is forward, counter-clockwise.

    Slot ``k`` covers ``[k, k+1) * 360/bins`` degrees measured from the robot's
    heading. Invalid returns become ``None`` rather than ``0.0`` — a zero would
    render as an obstacle touching the robot. Where several beams land in one
    slot the nearest wins, which keeps obstacles from being hidden.

    ``angle_offset`` (radians) rotates the whole sweep, for a LiDAR whose zero
    does not point along the robot's forward axis.
    """
    slots: List[Optional[float]] = [None] * bins
    values = np.asarray(ranges, dtype=np.float64)
    if values.size == 0:
        return slots

    angles = angle_min + np.arange(values.size) * angle_increment + angle_offset
    valid = np.isfinite(values) & (values >= range_min) & (values <= range_max)
    if not valid.any():
        return slots

    two_pi = 2.0 * math.pi
    # The sweep can span slightly over 360 degrees, so wrap before binning.
    indices = np.floor((angles[valid] % two_pi) / two_pi * bins).astype(int) % bins
    for slot, distance in zip(indices.tolist(), values[valid].tolist()):
        current = slots[slot]
        if current is None or distance < current:
            slots[slot] = round(distance, 3)
    return slots


def yaw_to_heading_deg(yaw: float) -> float:
    """Return yaw in radians as a 0-360 degree counter-clockwise heading."""
    return round(math.degrees(yaw) % 360.0, 2)


def apply_pose(points: np.ndarray, x: float, y: float, yaw: float) -> np.ndarray:
    """Return ``points`` rotated by ``yaw`` and translated by (x, y)."""
    if points.size == 0:
        return points
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[cos_yaw, -sin_yaw], [sin_yaw, cos_yaw]])
    return points @ rotation.T + np.array([x, y])


def world_to_pixel(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    resolution: float,
    height: int,
) -> Tuple[int, int]:
    """Return the (column, row) pixel of a map-frame point in the flipped image."""
    column = int(math.floor((x - origin_x) / resolution))
    row = height - 1 - int(math.floor((y - origin_y) / resolution))
    return column, row


def world_points_to_pixels(
    points: np.ndarray,
    origin_x: float,
    origin_y: float,
    resolution: float,
    height: int,
    width: int,
) -> np.ndarray:
    """Return in-bounds (column, row) integer pixels for map-frame points."""
    if points.size == 0:
        return np.empty((0, 2), dtype=int)
    columns = np.floor((points[:, 0] - origin_x) / resolution).astype(int)
    rows = height - 1 - np.floor((points[:, 1] - origin_y) / resolution).astype(int)
    inside = (columns >= 0) & (columns < width) & (rows >= 0) & (rows < height)
    return np.column_stack([columns[inside], rows[inside]])


def render_map_image(
    grid_rgb: np.ndarray,
    resolution: float,
    origin_x: float,
    origin_y: float,
    scan_points: Optional[np.ndarray] = None,
    pose: Optional[Tuple[float, float, float]] = None,
    scale: int = 1,
    dot_radius: int = 1,
) -> Image.Image:
    """Return the map as a PIL image with the scan and robot pose drawn on it."""
    height, width = grid_rgb.shape[:2]
    image = Image.fromarray(grid_rgb, mode="RGB")
    draw = ImageDraw.Draw(image)

    if scan_points is not None and len(scan_points):
        pixels = world_points_to_pixels(
            scan_points, origin_x, origin_y, resolution, height, width
        )
        for column, row in pixels:
            draw.ellipse(
                [column - dot_radius, row - dot_radius,
                 column + dot_radius, row + dot_radius],
                fill=SCAN_COLOR,
            )

    if pose is not None:
        pose_x, pose_y, yaw = pose
        column, row = world_to_pixel(
            pose_x, pose_y, origin_x, origin_y, resolution, height
        )
        arrow = max(4, int(round(0.25 / resolution)))
        draw.line(
            [column, row,
             column + int(arrow * math.cos(yaw)), row - int(arrow * math.sin(yaw))],
            fill=HEADING_COLOR,
            width=2,
        )
        marker = max(2, dot_radius + 2)
        draw.ellipse(
            [column - marker, row - marker, column + marker, row + marker],
            fill=ROBOT_COLOR,
        )

    if scale > 1:
        image = image.resize((width * scale, height * scale), Image.NEAREST)
    return image


def encode_png(image: Image.Image, optimize: bool = True) -> bytes:
    """Return the PNG bytes of a PIL image."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=optimize)
    return buffer.getvalue()


def crop_to_known(
    grid: np.ndarray, margin_cells: int = 4
) -> Tuple[np.ndarray, int, int]:
    """Return the sub-grid covering explored cells plus (left, bottom) offsets.

    Cartographer allocates a large canvas that is mostly unknown; cropping it
    keeps the PNG small. The offsets are in cells relative to the original map
    origin so the caller can shift ``origin_x`` / ``origin_y`` accordingly.
    """
    known = np.argwhere(grid >= 0)
    if known.size == 0:
        return grid, 0, 0
    height, width = grid.shape
    top = max(0, int(known[:, 0].min()) - margin_cells)
    bottom = min(height, int(known[:, 0].max()) + margin_cells + 1)
    left = max(0, int(known[:, 1].min()) - margin_cells)
    right = min(width, int(known[:, 1].max()) + margin_cells + 1)
    cropped = grid[top:bottom, left:right]
    # ``grid`` is top-down, so the bottom offset counts rows below the crop.
    return cropped, left, height - bottom


def scan_payload_points(points: np.ndarray, decimals: int = 3) -> List[List[float]]:
    """Return points as a rounded, JSON-serialisable list of [x, y] pairs."""
    if points.size == 0:
        return []
    return [[round(float(x), decimals), round(float(y), decimals)] for x, y in points]
