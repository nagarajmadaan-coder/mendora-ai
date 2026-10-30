"""Technician discovery fixes: area matching, trade names, empty-state messages, repeatable sample seed."""

import pytest
from fastapi.testclient import TestClient

from app.cli import SAMPLE_TECHNICIANS, seed_demo
from app.main import create_app
from app.models import TechnicianProfile, User
from app.services.technicians import area_key, query_area_keys
from conftest import make_settings


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """An app with the sample technicians seeded (demo mode on, as in development)."""
    settings = make_settings(tmp_path, environment="development")
    monkeypatch.setenv("MENDORA_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("MENDORA_ENVIRONMENT", "development")
    from app.config import get_settings

    get_settings.cache_clear()
    assert seed_demo("sample-pass-123") == 0
    get_settings.cache_clear()
    with TestClient(create_app(settings)) as c:
        yield c


def names(client, **params):
    r = client.get("/api/technicians", params=params)
    assert r.status_code == 200, r.text
    return [x["technician"]["display_name"] for x in r.json()["results"]], r.json()


# ---------- area normalisation ----------


@pytest.mark.parametrize(
    "a, b",
    [
        ("Indira Nagar", "indiranagar"),
        ("INDIRA-NAGAR", "indiranagar"),
        ("560 001", "560001"),
        ("Bangalore", "bengaluru"),
        ("New Delhi", "delhi"),
        ("T. Nagar", "t nagar"),
    ],
)
def test_area_keys_ignore_case_spaces_punctuation_and_aliases(a, b):
    assert area_key(a) == area_key(b)


def test_query_is_split_into_parts():
    assert {"koramangala", "bengaluru"} <= query_area_keys("Koramangala, Bangalore")


def test_different_postal_codes_do_not_match():
    assert area_key("560002") != area_key("560001")  # no guessing about nearby codes


# ---------- searches for all three trades ----------


@pytest.mark.parametrize("trade", ["plumbing", "electrical", "carpentry"])
def test_every_trade_returns_its_samples(demo, trade):
    found, body = names(demo, trade=trade)
    assert len(found) == 2 and all("(demo)" in n for n in found)
    assert body["demo_mode"] is True and body["message"] is None
    assert all(r["technician"]["trade"] == trade and r["technician"]["is_sample"] for r in body["results"])


def test_trade_is_case_insensitive_and_unknown_trade_is_explained(demo):
    assert len(names(demo, trade="Plumbing")[0]) == 2
    r = demo.get("/api/technicians", params={"trade": "roofing"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_trade"
    assert "plumbing, electrical or carpentry" in r.json()["error"]["message"]


@pytest.mark.parametrize(
    "area, expected",
    [
        ("560001", ["Sample Plumber A (demo)"]),
        ("560 001", ["Sample Plumber A (demo)"]),
        ("Indira Nagar", ["Sample Plumber A (demo)"]),
        ("Bangalore", ["Sample Plumber A (demo)"]),
        ("Indiranagar, Bengaluru", ["Sample Plumber A (demo)"]),
        ("Chennai", ["Sample Plumber B (demo)"]),
        ("madras", ["Sample Plumber B (demo)"]),
    ],
)
def test_matching_areas(demo, area, expected):
    found, body = names(demo, trade="plumbing", area=area)
    assert found == expected
    assert any(reason.startswith("Covers your area (") for reason in body["results"][0]["match_reasons"])


def test_non_matching_area_explains_and_lists_covered_areas(demo):
    found, body = names(demo, trade="plumbing", area="Kolkata")
    assert found == []
    assert "No plumbing technicians list 'Kolkata'" in body["message"]
    assert "chennai" in body["covered_areas"] and "560001" in body["covered_areas"]
    assert "connaught place" not in body["covered_areas"]  # carpentry only


def test_filter_explains_when_area_matches_but_filter_excludes(demo):
    found, body = names(demo, trade="plumbing", area="Chennai", available="true")
    assert found == []  # the Chennai sample plumber is "busy"
    assert "none are accepting requests now" in body["message"] and body["covered_areas"] == []


def test_unavailable_sample_is_listed_last_and_marked(demo):
    found, body = names(demo, trade="carpentry")
    assert found[-1] == "Sample Carpenter B (demo)"
    assert "Not taking new requests right now" in body["results"][-1]["match_reasons"]


# ---------- seed is repeatable ----------


def test_seed_updates_instead_of_duplicating(demo):
    factory = demo.app.state.session_factory
    with factory() as db:
        p = db.query(TechnicianProfile).filter(TechnicianProfile.display_name == "Sample Plumber B (demo)").one()
        p.service_areas = ["somewhere-else"]
        db.commit()
    assert seed_demo("another-password") == 0
    with factory() as db:
        assert db.query(TechnicianProfile).count() == len(SAMPLE_TECHNICIANS)
        assert db.query(User).filter(User.email.like("sample.%@demo.mendora.local")).count() == len(SAMPLE_TECHNICIANS)
        p = db.query(TechnicianProfile).filter(TechnicianProfile.display_name == "Sample Plumber B (demo)").one()
        assert p.service_areas == ["600017", "t nagar", "chennai"] and p.is_sample and p.verification_status == "unverified"
    # old password still works (existing accounts keep theirs)
    r = demo.post("/api/auth/login", json={"email": "sample.plumbing.1@demo.mendora.local", "password": "sample-pass-123"})
    assert r.status_code == 200


def test_samples_never_claim_verification_or_reviews(demo):
    _, body = names(demo)
    assert body["total"] == 6
    for r in body["results"]:
        t = r["technician"]
        assert t["verification_label"] == "Demo sample (not verified)" and t["verification_status"] == "unverified"
        assert t["reviews"]["count"] == 0 and t["reviews"]["average"] is None
        assert "Verified by a MENDORA admin" not in r["match_reasons"]


# ---------- empty database / demo mode off ----------


def test_empty_database_suggests_seed(client):
    _, body = names(client, trade="electrical")
    assert body["total"] == 0 and "python -m app.cli seed-demo" in body["message"]


def test_demo_off_explains_hidden_samples(tmp_path, monkeypatch):
    settings = make_settings(tmp_path, environment="development")
    monkeypatch.setenv("MENDORA_DATABASE_URL", settings.database_url)
    from app.config import get_settings

    get_settings.cache_clear()
    seed_demo("sample-pass-123")
    get_settings.cache_clear()
    with TestClient(create_app(make_settings(tmp_path, environment="development", demo_mode=False))) as c:
        _, body = names(c, trade="plumbing")
        assert body["total"] == 0 and "demo mode is off" in body["message"]


# ---------- approximate distance + map points (merged feature) ----------


def test_approx_distance_between_area_centres(demo):
    _, body = names(demo, trade="plumbing", area="Koramangala, Bengaluru")
    assert body["search_point"]["label"].startswith("Koramangala") and body["search_point"]["approximate"] is True
    _, body = names(demo, trade="plumbing")
    assert body["search_point"] is None and all(r["approx_distance_km"] is None for r in body["results"])
    assert all(r["map_point"] for r in body["results"])  # every sample has a known area centre


def test_distance_is_rounded_and_labelled_not_nearest(demo):
    r = demo.get("/api/technicians", params={"trade": "electrical", "area": "Indiranagar"}).json()
    # Electrician A covers 560001/560034/koramangala/bengaluru; Indiranagar itself isn't covered → no results, but the centre is known
    assert r["search_point"]["label"] == "Indiranagar"
    r = demo.get("/api/technicians", params={"trade": "plumbing", "area": "560038"}).json()
    m = r["results"][0]
    assert m["approx_distance_km"] == 0.5  # same area → minimum "about 0.5 km", never 0
    assert any("between area centres (approximate)" in x for x in m["match_reasons"])
    assert "nearest" not in " ".join(m["match_reasons"]).lower() and "not your address" in r["sort_note"]


def test_haversine_sanity():
    from app.services.areas import AREA_CENTRES, approx_km, km_between

    blr, che = AREA_CENTRES["bengaluru"], AREA_CENTRES["chennai"]
    assert 280 < km_between(blr, che) < 300  # ~290 km straight line
    assert approx_km(0.1) == 0.5 and approx_km(3.26) == 3.5
