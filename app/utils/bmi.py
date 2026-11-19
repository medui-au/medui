"""Which height a BMI is worked out from.

The latest height, as Best Practice records it, at any age, except that a height measured
before 18 is not used for a patient who is now 18 or older: their BMI is left out rather
than worked out from a childhood height. Weight and height are still shown. The latest
weight with the latest adult height is used even when they were measured on different days,
unlike Best Practice's own BMI, which needs both on the same day.
"""

ADULT_AGE = 18


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bmi_height(demo: dict):
    """The height in metres to work BMI out from, or None."""
    try:
        height = float(demo.get('HEIGHTVALUE') or 0)
    except (TypeError, ValueError):
        return None
    if height <= 0:
        return None
    height_age, age_now = _int(demo.get('HEIGHT_AGE')), _int(demo.get('AGE'))
    if height_age is None or height_age >= ADULT_AGE:
        return height        # no date of birth: as before
    if age_now is not None and age_now < ADULT_AGE:
        return height        # still a child: their latest height
    return None
