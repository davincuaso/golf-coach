"""Known geometry and timing, independent of model accuracy."""

import math


def pose_document(*, spine_at=None, hand_at=None, timestamp_source="decoder_pts"):
    frames = []
    for i in range(121):
        time = i / 60
        angle = spine_at(time) if spine_at else 45
        shoulder = [
            500 + 200 * math.sin(math.radians(angle)),
            700 - 200 * math.cos(math.radians(angle)),
        ]
        hand_distance = hand_at(time) if hand_at else 0
        coordinates = {
            "left_shoulder": [shoulder[0] - 30, shoulder[1]],
            "right_shoulder": [shoulder[0] + 30, shoulder[1]],
            "left_hip": [470, 700],
            "right_hip": [530, 700],
            "left_wrist": [490 + 200 * hand_distance, 800],
            "right_wrist": [510 + 200 * hand_distance, 800],
        }
        frames.append(
            {
                "frame_index": i,
                "timestamp_seconds": time,
                "landmarks": {
                    name: {
                        "xy_px": xy,
                        "confidence": 0.95,
                        "observed": True,
                        "interpolated": False,
                        "filtered": True,
                    }
                    for name, xy in coordinates.items()
                },
                "angles_deg": {"spine_tilt_2d": -999},
            }
        )
    return {
        "schema_version": "1.0.0",
        "video": {
            "width": 1200,
            "height": 1000,
            "frame_count": 121,
            "nominal_fps": 60,
            "timestamp_source": timestamp_source,
        },
        "frames": frames,
    }


def swing_distance(time):
    if time < 0.3:
        return 0
    if time <= 1.2:
        return (time - 0.3) / 0.9
    if time <= 1.5:
        return 1 - (time - 1.2) / 0.3
    return 0


MARKERS = {"start_seconds": 0.3, "top_seconds": 1.2, "impact_seconds": 1.5}
