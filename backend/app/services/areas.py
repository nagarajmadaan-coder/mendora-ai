"""
Approximate area centres (merged feature: map + distance).

MENDORA doesn't know anyone's exact location. For areas listed here it uses a rough CENTRE point,
so a distance is only "about X km between area centres" — never an exact distance and never "nearest".
Coordinates are approximate public centre points (rounded); add more areas as needed.
"""

import math

from .technicians import area_key

# key (see area_key) → (latitude, longitude, display label)
AREA_CENTRES: dict[str, tuple[float, float, str]] = {
    # Bengaluru
    "bengaluru": (12.9716, 77.5946, "Bengaluru (city centre)"),
    "560001": (12.9757, 77.6050, "560001 · MG Road area"),
    "560038": (12.9784, 77.6408, "560038 · Indiranagar"),
    "indiranagar": (12.9784, 77.6408, "Indiranagar"),
    "560034": (12.9352, 77.6245, "560034 · Koramangala"),
    "koramangala": (12.9352, 77.6245, "Koramangala"),
    "560095": (12.9343, 77.6260, "560095 · Koramangala 6th Block"),
    "560066": (12.9698, 77.7500, "560066 · Whitefield"),
    "whitefield": (12.9698, 77.7500, "Whitefield"),
    "560102": (12.9116, 77.6474, "560102 · HSR Layout"),
    "hsrlayout": (12.9116, 77.6474, "HSR Layout"),
    "560011": (12.9308, 77.5838, "560011 · Jayanagar"),
    "jayanagar": (12.9308, 77.5838, "Jayanagar"),
    # Chennai
    "chennai": (13.0827, 80.2707, "Chennai (city centre)"),
    "600017": (13.0418, 80.2341, "600017 · T. Nagar"),
    "tnagar": (13.0418, 80.2341, "T. Nagar"),
    "600020": (13.0067, 80.2570, "600020 · Adyar"),
    "adyar": (13.0067, 80.2570, "Adyar"),
    # Mumbai
    "mumbai": (19.0760, 72.8777, "Mumbai (city centre)"),
    "400053": (19.1364, 72.8296, "400053 · Andheri West"),
    "andheri": (19.1136, 72.8697, "Andheri"),
    "400050": (19.0596, 72.8295, "400050 · Bandra West"),
    "bandra": (19.0596, 72.8295, "Bandra"),
    # Delhi
    "delhi": (28.6139, 77.2090, "Delhi (city centre)"),
    "110001": (28.6315, 77.2167, "110001 · Connaught Place"),
    "connaughtplace": (28.6315, 77.2167, "Connaught Place"),
    # Others
    "hyderabad": (17.3850, 78.4867, "Hyderabad (city centre)"),
    "kolkata": (22.5726, 88.3639, "Kolkata (city centre)"),
    "pune": (18.5204, 73.8567, "Pune (city centre)"),
}


def centre(area: str | None) -> tuple[float, float, str] | None:
    if not area or not area.strip():
        return None
    from .technicians import query_area_keys

    for key in sorted(query_area_keys(area), key=len, reverse=True):  # most specific part first
        if key in AREA_CENTRES:
            return AREA_CENTRES[key]
    return None


def km_between(a: tuple[float, float, str], b: tuple[float, float, str]) -> float:
    """Great-circle (haversine) distance between two centre points, in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def approx_km(km: float) -> float:
    return max(0.5, round(km * 2) / 2)  # nearest 0.5 km, never "0 km"


def technician_point(service_areas: list[str]) -> tuple[float, float, str] | None:
    """Map marker for a technician: the centre of their first area MENDORA knows (most specific first)."""
    known = [AREA_CENTRES[area_key(a)] for a in service_areas if area_key(a) in AREA_CENTRES]
    specific = [c for c in known if "city centre" not in c[2]]
    return (specific or known or [None])[0]


def nearest_centre_km(customer: tuple[float, float, str], service_areas: list[str]) -> float | None:
    points = [AREA_CENTRES[area_key(a)] for a in service_areas if area_key(a) in AREA_CENTRES]
    return min((km_between(customer, p) for p in points), default=None)


__all__ = ["AREA_CENTRES", "centre", "km_between", "approx_km", "technician_point", "nearest_centre_km"]
