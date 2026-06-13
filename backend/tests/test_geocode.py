import json
from pathlib import Path

from cloudy.geocode import nominatim, photon

FIXTURES = Path(__file__).parent / "fixtures"


def test_photon_parse_real_response() -> None:
    payload = json.loads((FIXTURES / "photon-drottninggatan.json").read_text())
    candidates = photon.parse(payload)
    assert candidates
    first = candidates[0]
    assert "Drottninggatan" in first.label
    assert 59.0 < first.lat < 60.0
    assert 17.5 < first.lon < 18.5


def test_nominatim_parse_real_response() -> None:
    payload = json.loads((FIXTURES / "nominatim-drottninggatan.json").read_text())
    candidates = nominatim.parse(payload)
    assert candidates
    first = candidates[0]
    assert "Drottninggatan" in first.label
    assert 59.0 < first.lat < 60.0


def test_photon_parse_tolerates_garbage() -> None:
    assert photon.parse({"features": [{"nope": 1}, None]}) == ()
    assert photon.parse({}) == ()
