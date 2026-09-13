import array
import math

import numpy as np
import pytest

from lumi_map_bridge.map_encode import (
    OCCUPIED_BLACK,
    FREE_WHITE,
    UNKNOWN_GRAY,
    apply_pose,
    crop_to_known,
    encode_png,
    grid_to_array,
    grid_to_rgb,
    quaternion_to_yaw,
    render_map_image,
    scan_payload_points,
    scan_to_bins,
    scan_to_points,
    world_points_to_pixels,
    world_to_pixel,
    yaw_to_heading_deg,
)


def bins_from(ranges, bins=360, offset=0.0, n=None):
    """Bin a full -pi..pi sweep of the given ranges."""
    count = len(ranges) if n is None else n
    return scan_to_bins(
        ranges, -math.pi, 2 * math.pi / count, 0.1, 12.0, bins=bins, angle_offset=offset
    )


def test_grid_to_array_flips_ros_row_order():
    # ROS row 0 is the bottom row; the image must have it last.
    grid = grid_to_array(array.array("b", [0, 0, 100, 100]), height=2, width=2)
    assert grid.tolist() == [[100, 100], [0, 0]]


def test_grid_to_array_accepts_plain_lists():
    assert grid_to_array([-1, 0, 50, 100], 2, 2).shape == (2, 2)


def test_grid_to_array_rejects_size_mismatch():
    with pytest.raises(ValueError):
        grid_to_array([0, 0, 0], 2, 2)


def test_grid_to_rgb_maps_three_states():
    rgb = grid_to_rgb(np.array([[-1, 0, 100]], dtype=np.int8))
    assert rgb.shape == (1, 3, 3)
    assert rgb[0, 0, 0] == UNKNOWN_GRAY
    assert rgb[0, 1, 0] == FREE_WHITE
    assert rgb[0, 2, 0] == OCCUPIED_BLACK


def test_scan_to_points_drops_invalid_returns():
    # 0.0 is the driver's "no return" value (invalid_range_is_inf is false).
    points = scan_to_points(
        [0.0, 1.0, float("inf"), float("nan"), 99.0],
        angle_min=0.0,
        angle_increment=math.pi / 2,
        range_min=0.1,
        range_max=12.0,
    )
    assert len(points) == 1
    assert points[0] == pytest.approx([0.0, 1.0], abs=1e-9)


def test_scan_to_points_thins_evenly_and_keeps_extremes():
    points = scan_to_points(
        [1.0] * 100, 0.0, 0.01, 0.1, 12.0, max_points=10
    )
    assert len(points) == 10


def test_scan_to_points_handles_empty_scan():
    assert scan_to_points([], 0.0, 0.01, 0.1, 12.0).shape == (0, 2)


def test_apply_pose_rotates_then_translates():
    moved = apply_pose(np.array([[1.0, 0.0]]), 2.0, 3.0, math.pi / 2)
    assert moved[0] == pytest.approx([2.0, 4.0], abs=1e-9)


def test_quaternion_to_yaw_round_trip():
    yaw = 1.1
    quaternion = (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))
    assert quaternion_to_yaw(*quaternion) == pytest.approx(yaw)


def test_world_to_pixel_puts_origin_at_bottom_left():
    # The map origin is the bottom-left corner, so it is the last image row.
    assert world_to_pixel(0.0, 0.0, 0.0, 0.0, 0.05, height=100) == (0, 99)


def test_world_to_pixel_moves_up_as_y_grows():
    assert world_to_pixel(0.0, 1.0, 0.0, 0.0, 0.05, height=100) == (0, 79)


def test_world_points_to_pixels_drops_out_of_bounds():
    points = np.array([[0.0, 0.0], [-5.0, 0.0], [100.0, 0.0]])
    pixels = world_points_to_pixels(points, 0.0, 0.0, 0.05, height=10, width=10)
    assert pixels.tolist() == [[0, 9]]


def test_crop_to_known_trims_unknown_border():
    grid = np.full((20, 20), -1, dtype=np.int8)
    grid[8:10, 5:7] = 0
    cropped, left, bottom = crop_to_known(grid, margin_cells=1)
    assert cropped.shape == (4, 4)
    assert left == 4
    # rows 0..7 are above the crop, rows 11..19 below it in top-down order
    assert bottom == 20 - 11


def test_crop_to_known_passes_through_empty_map():
    grid = np.full((5, 5), -1, dtype=np.int8)
    cropped, left, bottom = crop_to_known(grid)
    assert cropped.shape == (5, 5) and left == 0 and bottom == 0


def test_render_map_image_draws_overlay_without_resizing():
    grid = np.zeros((40, 40), dtype=np.int8)
    image = render_map_image(
        grid_to_rgb(grid),
        resolution=0.05,
        origin_x=0.0,
        origin_y=0.0,
        scan_points=np.array([[1.0, 1.0]]),
        pose=(0.5, 0.5, 0.0),
    )
    assert image.size == (40, 40)
    colors = {color for _, color in image.getcolors(maxcolors=1 << 16)}
    assert (255, 255, 255) in colors  # free space survives
    assert len(colors) > 1  # overlay actually painted something


def test_render_map_image_scales_nearest():
    image = render_map_image(grid_to_rgb(np.zeros((10, 10), np.int8)), 0.05, 0, 0, scale=3)
    assert image.size == (30, 30)


def test_encode_png_returns_png_magic():
    image = render_map_image(grid_to_rgb(np.zeros((8, 8), np.int8)), 0.05, 0, 0)
    assert encode_png(image).startswith(b"\x89PNG\r\n\x1a\n")


def test_scan_to_bins_returns_fixed_length_with_none_gaps():
    slots = bins_from([0.0] * 720)  # every return invalid
    assert len(slots) == 360
    assert all(slot is None for slot in slots)


def test_scan_to_bins_puts_forward_beam_in_slot_zero():
    # 720 beams from -pi: index 360 is angle 0, i.e. straight ahead.
    ranges = [0.0] * 720
    ranges[360] = 2.5
    slots = bins_from(ranges)
    assert slots[0] == 2.5
    assert sum(slot is not None for slot in slots) == 1


def test_scan_to_bins_puts_left_ninety_in_slot_ninety():
    # +90 degrees is counter-clockwise (left) in ROS, and 90 slots in.
    ranges = [0.0] * 720
    ranges[360 + 180] = 3.0
    assert bins_from(ranges)[90] == 3.0


def test_scan_to_bins_wraps_a_sweep_wider_than_360_degrees():
    # The real X4-Pro reports 430 beams spanning 360.84 degrees; the overhang
    # must wrap onto slot 0 rather than overflow the array.
    ranges = [1.0] * 430
    slots = scan_to_bins(ranges, -math.pi, 0.01464612, 0.1, 12.0, bins=360)
    assert len(slots) == 360
    assert slots[0] == 1.0


def test_scan_to_bins_keeps_the_nearest_of_colliding_beams():
    ranges = [0.0] * 720
    ranges[360], ranges[361] = 5.0, 2.0  # both land in slot 0
    assert bins_from(ranges)[0] == 2.0


def test_scan_to_bins_drops_out_of_range_returns():
    ranges = [0.0] * 720
    ranges[360] = 99.0  # beyond range_max
    ranges[361] = 0.05  # below range_min
    assert all(slot is None for slot in bins_from(ranges))


def test_scan_to_bins_applies_angle_offset():
    ranges = [0.0] * 720
    ranges[360] = 2.5  # forward
    slots = bins_from(ranges, offset=math.pi / 2)  # rotate 90 deg CCW
    assert slots[0] is None
    assert slots[90] == 2.5


def test_scan_to_bins_honours_a_finer_bin_count():
    ranges = [0.0] * 720
    ranges[360] = 2.5
    slots = bins_from(ranges, bins=1440)
    assert len(slots) == 1440 and slots[0] == 2.5


def test_scan_to_bins_handles_empty_scan():
    assert scan_to_bins([], -math.pi, 0.01, 0.1, 12.0) == [None] * 360


def test_yaw_to_heading_deg_wraps_negatives_into_0_360():
    assert yaw_to_heading_deg(0.0) == 0.0
    assert yaw_to_heading_deg(math.pi / 2) == 90.0
    assert yaw_to_heading_deg(-math.pi / 2) == 270.0
    assert yaw_to_heading_deg(2 * math.pi) == 0.0


def test_scan_payload_points_rounds_and_serialises():
    assert scan_payload_points(np.array([[1.23456, -0.5]])) == [[1.235, -0.5]]
    assert scan_payload_points(np.empty((0, 2))) == []
