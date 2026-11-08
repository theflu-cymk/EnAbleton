"""Single finite-number validator shared by Live guards, planners and analysis."""

import math


def finite(value, label):
    """Return value as a float, rejecting booleans, non-numbers and NaN/inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    return float(value)
