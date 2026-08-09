"""Site-Standard 25: round every constructible output (spacing, dimension)
to a multiple of 25 mm, direction-aware so the rounding never invalidates
the check that produced the value.

Areas, capacities, and other non-constructible outputs are never rounded --
do not use these on Ast/Pu/Mu/etc.
"""

import math


def site_spacing(x: float, cap: float | None = None) -> float:
    """Maximum-allowed constructible spacing (stirrup pitch, tie pitch, bar
    spacing): floor to the nearest lower 25 mm. If `cap` (the code-maximum
    spacing) is given, clamp to it BEFORE flooring, so the result can never
    exceed the code limit. Flooring a value already <= cap can only make it
    smaller, so `result <= cap` always holds."""
    v = x if cap is None else min(x, cap)
    return math.floor(v / 25.0) * 25.0


def site_dimension(x: float) -> float:
    """Minimum-required constructible dimension (member depth/width, footing
    plan size/depth, Ld, lap length, cover): ceil to the nearest higher 25
    mm. Ceiling a value already >= required can only make it bigger, so
    `result >= x` always holds."""
    return math.ceil(x / 25.0) * 25.0
