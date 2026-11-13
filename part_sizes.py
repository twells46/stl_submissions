"""Fall game size groups, measured by oriented exterior bounding-box dimensions."""

import math


SIZE_CHECK_VERSION = "3"
# Dimensions may be permuted, but all three limits must be satisfied.
SIZE_GROUPS = (
    ("small", (60, 60, 20), 6),
    ("mid-size", (220, 220, 80), 2),
    ("large", (220, 220, 250), 1),
)


def rounded_extents_mm(extents):
    # Blender's float32 projections can put an exact boundary just above an
    # integer. Snap only that numerical noise before rounding measurements up.
    return tuple(
        round(value) if math.isclose(value, round(value), rel_tol=0, abs_tol=1e-4)
        else math.ceil(value)
        for value in extents
    )


def size_group_for_extents(extents):
    measured = sorted(rounded_extents_mm(extents))
    for name, dimensions, _ in SIZE_GROUPS:
        if all(value <= limit for value, limit in zip(measured, sorted(dimensions))):
            return name
    return None
