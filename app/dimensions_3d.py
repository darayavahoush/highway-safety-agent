"""
3D Vehicle Dimension Estimation & Projection Engine.

Provides:
1. Standard real-world physical dimensions (Length, Width, Height in meters),
   footprint area (m²), volume (m³), and mass priors for each vehicle class.
2. Ground-plane 3D coordinate estimation from 2D bounding boxes under drone/overhead views.
3. 3D bounding cuboid projection helper for drawing perspective 3D boxes directly
   onto 2D OpenCV video frames.
"""

import math
from typing import Dict, List, Tuple, Any
import cv2
import numpy as np


# Standard automotive physical dimension priors (metric in meters)
# Derived from ISO / EuroNCAP / Federal Highway Administration averages
VEHICLE_DIMENSION_PRIORS: Dict[str, Dict[str, float]] = {
    "Car": {
        "length_m": 4.50,
        "width_m": 1.82,
        "height_m": 1.48,
        "mass_kg": 1500.0,
        "color_hex": "#38bdf8",  # Sky blue
        "color_bgr": (248, 189, 56),
    },
    "Van": {
        "length_m": 5.35,
        "width_m": 2.02,
        "height_m": 2.25,
        "mass_kg": 2400.0,
        "color_hex": "#34d399",  # Emerald
        "color_bgr": (153, 211, 52),
    },
    "Truck": {
        "length_m": 8.80,
        "width_m": 2.50,
        "height_m": 3.40,
        "mass_kg": 11500.0,
        "color_hex": "#a78bfa",  # Purple
        "color_bgr": (250, 139, 167),
    },
    "Bus": {
        "length_m": 12.00,
        "width_m": 2.55,
        "height_m": 3.20,
        "mass_kg": 13800.0,
        "color_hex": "#fbbf24",  # Amber
        "color_bgr": (36, 191, 251),
    },
    "Motorbike": {
        "length_m": 2.10,
        "width_m": 0.82,
        "height_m": 1.15,
        "mass_kg": 210.0,
        "color_hex": "#fb7185",  # Coral rose
        "color_bgr": (133, 113, 251),
    },
    "Vehicle": {
        "length_m": 4.60,
        "width_m": 1.88,
        "height_m": 1.55,
        "mass_kg": 1700.0,
        "color_hex": "#4fd1c5",  # Teal fallback
        "color_bgr": (197, 209, 79),
    },
}


def get_vehicle_dimensions(label: str) -> Dict[str, Any]:
    """Returns metric dimension specs, area, and volume for a vehicle class."""
    specs = VEHICLE_DIMENSION_PRIORS.get(label, VEHICLE_DIMENSION_PRIORS["Vehicle"])
    l = specs["length_m"]
    w = specs["width_m"]
    h = specs["height_m"]
    return {
        "length_m": l,
        "width_m": w,
        "height_m": h,
        "footprint_m2": round(l * w, 2),
        "volume_m3": round(l * w * h, 2),
        "mass_kg": specs["mass_kg"],
        "color_hex": specs["color_hex"],
    }


def estimate_3d_pose(
    x: float, y: float, bw: float, bh: float, frame_w: int, frame_h: int,
    ground_span_x_m: float = 80.0, ground_span_z_m: float = 45.0,
    motion_dx: float = 0.0, motion_dy: float = 0.0,
) -> Tuple[float, float, float, float]:
    """
    Estimates 3D ground position (X, Y, Z in meters) and yaw angle (degrees)
    assuming ground plane view from aerial drone.
    X: left-to-right (-half .. +half)
    Y: ground height (elevation = 0)
    Z: near-to-far (-half .. +half)
    yaw: 0..360 orientation degrees
    """
    cx = x + bw / 2.0
    cy = y + bh / 2.0

    # Normalized image coordinates (-0.5 to +0.5)
    nx = (cx / float(frame_w)) - 0.5
    ny = (cy / float(frame_h)) - 0.5

    world_x = nx * ground_span_x_m
    world_z = ny * ground_span_z_m
    world_y = 0.0  # On ground plane

    # Estimate heading/yaw
    if abs(motion_dx) > 0.5 or abs(motion_dy) > 0.5:
        # True heading from tracking motion
        yaw_rad = math.atan2(motion_dy, motion_dx)
        yaw_deg = math.degrees(yaw_rad) % 360.0
    else:
        # Orientation from aspect ratio
        if bw >= bh:
            yaw_deg = 0.0 if nx >= 0 else 180.0
        else:
            yaw_deg = 90.0 if ny >= 0 else 270.0

    return round(world_x, 2), round(world_y, 2), round(world_z, 2), round(yaw_deg, 1)


def build_3d_vehicle_record(
    track_id: int, label: str, conf: float, box: Tuple[float, float, float, float],
    frame_w: int, frame_h: int, motion_dx: float = 0.0, motion_dy: float = 0.0,
) -> Dict[str, Any]:
    """Produces a complete 3D vehicle representation for API / WebSocket."""
    x, y, bw, bh = box
    dims = get_vehicle_dimensions(label)
    wx, wy, wz, yaw = estimate_3d_pose(
        x, y, bw, bh, frame_w, frame_h, motion_dx=motion_dx, motion_dy=motion_dy
    )

    return {
        "id": track_id,
        "label": label,
        "confidence": round(float(conf), 2),
        "box_2d": [round(float(x), 1), round(float(y), 1), round(float(bw), 1), round(float(bh), 1)],
        "center_2d": [round(x + bw / 2.0, 1), round(y + bh / 2.0, 1)],
        "dimensions_3d": dims,
        "position_3d": {
            "x": wx,
            "y": wy,
            "z": wz,
        },
        "yaw_deg": yaw,
    }


def draw_3d_bounding_box(
    frame: np.ndarray,
    x: Any,
    y: float = 0.0,
    bw: float = 0.0,
    bh: float = 0.0,
    label: str = "Car",
    conf: float = 1.0,
    track_id: int = 0,
    show_dims: bool = False,
    is_selected: bool = False,
) -> np.ndarray:
    """
    Projects a clean, non-intrusive 3D isometric bounding cuboid onto a 2D image frame:
    - Base footprint on ground
    - Thin vertical height pillars
    - Elevated roof wireframe
    - Highlighted targeting reticle + dimension placard ONLY when is_selected or show_dims is True.
    """
    if isinstance(x, dict):
        v = x
        box = v.get("box_2d", [0, 0, 0, 0])
        x, y, bw, bh = box[0], box[1], box[2], box[3]
        label = v.get("label", "Car")
        conf = v.get("confidence", 1.0)
        track_id = v.get("id", 0)

    specs = VEHICLE_DIMENSION_PRIORS.get(label, VEHICLE_DIMENSION_PRIORS["Vehicle"])
    base_color = specs["color_bgr"]

    ix, iy, ibw, ibh = int(x), int(y), int(bw), int(bh)
    h_offset = max(4, int(ibh * 0.28))

    # Base rectangle (ground contact)
    b0 = (ix, iy + ibh)
    b1 = (ix + ibw, iy + ibh)
    b2 = (ix + ibw, iy + h_offset)
    b3 = (ix, iy + h_offset)

    # Roof rectangle (elevated in 3D)
    r0 = (ix, iy + ibh - h_offset)
    r1 = (ix + ibw, iy + ibh - h_offset)
    r2 = (ix + ibw, iy)
    r3 = (ix, iy)

    if is_selected:
        target_color = (0, 240, 255)  # Bright cyan-gold

        # Draw semi-transparent highlighted roof
        overlay = frame.copy()
        roof_pts = np.array([r0, r1, r2, r3], np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(overlay, [roof_pts], target_color)
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

        # Wireframe cuboid
        for p1, p2 in [
            (b0, b1), (b1, b2), (b2, b3), (b3, b0),
            (b0, r0), (b1, r1), (b2, r2), (b3, r3),
            (r0, r1), (r1, r2), (r2, r3), (r3, r0),
        ]:
            cv2.line(frame, p1, p2, target_color, 2, cv2.LINE_AA)

        # Tactical Corner Brackets around vehicle
        corner_len = max(6, min(14, int(min(ibw, ibh) * 0.35)))
        cx, cy = ix + ibw // 2, iy + ibh // 2
        cv2.drawMarker(frame, (cx, cy), target_color, cv2.MARKER_CROSS, 8, 1, cv2.LINE_AA)

        # Top-left corner
        cv2.line(frame, (ix, iy), (ix + corner_len, iy), target_color, 2, cv2.LINE_AA)
        cv2.line(frame, (ix, iy), (ix, iy + corner_len), target_color, 2, cv2.LINE_AA)
        # Top-right corner
        cv2.line(frame, (ix + ibw, iy), (ix + ibw - corner_len, iy), target_color, 2, cv2.LINE_AA)
        cv2.line(frame, (ix + ibw, iy), (ix + ibw, iy + corner_len), target_color, 2, cv2.LINE_AA)
        # Bottom-left corner
        cv2.line(frame, (ix, iy + ibh), (ix + corner_len, iy + ibh), target_color, 2, cv2.LINE_AA)
        cv2.line(frame, (ix, iy + ibh), (ix, iy + ibh - corner_len), target_color, 2, cv2.LINE_AA)
        # Bottom-right corner
        cv2.line(frame, (ix + ibw, iy + ibh), (ix + ibw - corner_len, iy + ibh), target_color, 2, cv2.LINE_AA)
        cv2.line(frame, (ix + ibw, iy + ibh), (ix + ibw, iy + ibh - corner_len), target_color, 2, cv2.LINE_AA)

        # Detailed Target HUD Callout Badge
        dim_str = f"TARGET #{track_id} {label.upper()} · {specs['length_m']}x{specs['width_m']}x{specs['height_m']}m"
        font_scale = 0.40
        (tw, th), _ = cv2.getTextSize(dim_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        tx = max(4, ix)
        ty = max(th + 6, iy - 6)
        cv2.rectangle(frame, (tx - 3, ty - th - 4), (tx + tw + 4, ty + 3), (15, 23, 42), -1)
        cv2.rectangle(frame, (tx - 3, ty - th - 4), (tx + tw + 4, ty + 3), target_color, 1)
        cv2.putText(frame, dim_str, (tx, ty - 1), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    else:
        # Non-selected vehicle: clean, lightweight 1px wireframe in class color
        cv2.line(frame, b0, b1, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b1, b2, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b2, b3, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b3, b0, base_color, 1, cv2.LINE_AA)

        cv2.line(frame, b0, r0, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b1, r1, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b2, r2, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, b3, r3, base_color, 1, cv2.LINE_AA)

        cv2.line(frame, r0, r1, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, r1, r2, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, r2, r3, base_color, 1, cv2.LINE_AA)
        cv2.line(frame, r3, r0, base_color, 1, cv2.LINE_AA)

        if show_dims:
            dim_str = f"{label} {specs['length_m']}x{specs['width_m']}m"
            font_scale = 0.32
            (tw, th), _ = cv2.getTextSize(dim_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            tx = ix
            ty = max(th + 4, iy - 3)
            cv2.rectangle(frame, (tx - 1, ty - th - 2), (tx + tw + 2, ty + 2), (15, 20, 28), -1)
            cv2.putText(frame, dim_str, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (220, 220, 220), 1, cv2.LINE_AA)

    return frame
