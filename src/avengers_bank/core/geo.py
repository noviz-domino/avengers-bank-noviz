from math import asin, cos, radians, sin, sqrt


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lat2 = radians(lat1), radians(lat2)
    delta_lon = radians(lon2 - lon1)
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 12_742_000 * asin(sqrt(min(1, a)))
