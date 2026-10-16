import time


def calculate_decay(
    base_weight: float,
    age_seconds: float,
    half_life_seconds: float | None = None,
) -> float:
    """Calculate exponential decay multiplier using half-life decay.
    Formula: weight * 0.5 ^ (age / half_life).
    If half_life is None or <= 0, no decay is applied (decay factor = 1.0).
    """
    if half_life_seconds is None or half_life_seconds <= 0:
        return round(float(base_weight), 4)

    age = max(0.0, float(age_seconds))
    decay_factor = 0.5 ** (age / float(half_life_seconds))
    return round(float(base_weight) * decay_factor, 4)


def decay_weight_days(
    weight: float,
    age_days: float,
    half_life_days: float = 30.0,
) -> float:
    """Compute effective weight of historical observations/evidence decayed over days."""
    return calculate_decay(
        base_weight=weight,
        age_seconds=age_days * 86400.0,
        half_life_seconds=half_life_days * 86400.0,
    )
