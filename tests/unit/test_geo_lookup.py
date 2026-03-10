import pytest
from unittest.mock import patch, MagicMock
from app.services.geo_lookup import (
    _normalize,
    _pick_name,
    _extract_polygons,
    _point_in_ring,
    _point_in_polygon,
    _contains,
    is_within_cuba_bounds,
    lookup_location,
    list_provinces,
    list_municipalities,
    municipalities_map,
    _cache,
)


class TestNormalize:
    def test_basic(self):
        assert _normalize("La Habana") == "la habana"

    def test_accents_removed(self):
        assert _normalize("Camagüey") == "camaguey"

    def test_empty(self):
        assert _normalize("") == ""
        assert _normalize(None) == ""


class TestPickName:
    def test_finds_first_key(self):
        props = {"name": "Havana", "province": "X"}
        assert _pick_name(props, ["province", "name"]) == "X"

    def test_skips_empty(self):
        props = {"name": "", "alt": "Havana"}
        assert _pick_name(props, ["name", "alt"]) == "Havana"

    def test_no_match(self):
        assert _pick_name({"a": 1}, ["x", "y"]) is None


class TestExtractPolygons:
    def test_polygon(self):
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        assert _extract_polygons(geom) == [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]

    def test_multi_polygon(self):
        coords = [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]
        geom = {"type": "MultiPolygon", "coordinates": coords}
        assert _extract_polygons(geom) == coords

    def test_none(self):
        assert _extract_polygons(None) == []

    def test_unknown_type(self):
        assert _extract_polygons({"type": "Point"}) == []


class TestPointInRing:
    def test_inside_square(self):
        ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        assert _point_in_ring((5, 5), ring) is True

    def test_outside_square(self):
        ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        assert _point_in_ring((15, 15), ring) is False

    def test_empty_ring(self):
        assert _point_in_ring((0, 0), []) is False

    def test_unclosed_ring(self):
        ring = [[0, 0], [10, 0], [10, 10], [0, 10]]
        assert _point_in_ring((5, 5), ring) is True


class TestPointInPolygon:
    def test_in_outer(self):
        polygon = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
        assert _point_in_polygon((5, 5), polygon) is True

    def test_in_hole(self):
        outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        hole = [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]
        assert _point_in_polygon((5, 5), [outer, hole]) is False

    def test_empty(self):
        assert _point_in_polygon((5, 5), []) is False


class TestContains:
    def test_in_one_polygon(self):
        polygon = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
        assert _contains((5, 5), [polygon]) is True

    def test_not_in_any(self):
        polygon = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
        assert _contains((50, 50), [polygon]) is False


class TestIsWithinCubaBounds:
    def test_havana(self):
        assert is_within_cuba_bounds(23.1136, -82.3666) is True

    def test_outside(self):
        assert is_within_cuba_bounds(40.0, -74.0) is False

    def test_invalid(self):
        assert is_within_cuba_bounds("abc", "def") is False


class TestLookupLocation:
    @patch("app.services.geo_lookup._load_layers")
    def test_returns_province_and_municipality(self, mock_load):
        square = [[[-83, 22], [-81, 22], [-81, 24], [-83, 24], [-83, 22]]]
        _cache["provinces"] = [{"name": "La Habana", "polygons": [square], "province": None}]
        _cache["municipalities"] = [{"name": "Playa", "polygons": [square], "province": "La Habana"}]
        prov, mun = lookup_location(23.0, -82.0)
        assert prov == "La Habana"
        assert mun == "Playa"

    @patch("app.services.geo_lookup._load_layers")
    def test_no_match(self, mock_load):
        _cache["provinces"] = []
        _cache["municipalities"] = []
        prov, mun = lookup_location(0.0, 0.0)
        assert prov is None
        assert mun is None

    @patch("app.services.geo_lookup._load_layers")
    def test_municipality_provides_province(self, mock_load):
        square = [[[-83, 22], [-81, 22], [-81, 24], [-83, 24], [-83, 22]]]
        _cache["provinces"] = []
        _cache["municipalities"] = [{"name": "Playa", "polygons": [square], "province": "La Habana"}]
        prov, mun = lookup_location(23.0, -82.0)
        assert prov == "La Habana"
        assert mun == "Playa"


class TestListProvinces:
    @patch("app.services.geo_lookup._load_layers")
    def test_from_cache(self, mock_load):
        _cache["provinces"] = [
            {"name": "B Province", "polygons": [], "province": None},
            {"name": "A Province", "polygons": [], "province": None},
        ]
        result = list_provinces()
        assert result == ["A Province", "B Province"]

    @patch("app.services.geo_lookup._load_layers")
    def test_fallback_to_static(self, mock_load):
        _cache["provinces"] = []
        _cache["municipalities"] = []
        result = list_provinces()
        assert "La Habana" in result


class TestListMunicipalities:
    @patch("app.services.geo_lookup._load_layers")
    def test_all(self, mock_load):
        _cache["municipalities"] = [
            {"name": "Playa", "province": "La Habana", "polygons": []},
            {"name": "Bayamo", "province": "Granma", "polygons": []},
        ]
        result = list_municipalities()
        assert "Playa" in result
        assert "Bayamo" in result

    @patch("app.services.geo_lookup._load_layers")
    def test_by_province(self, mock_load):
        _cache["municipalities"] = [
            {"name": "Playa", "province": "La Habana", "polygons": []},
            {"name": "Bayamo", "province": "Granma", "polygons": []},
        ]
        result = list_municipalities(province="La Habana")
        assert result == ["Playa"]


class TestMunicipalitiesMap:
    @patch("app.services.geo_lookup._load_layers")
    def test_from_cache(self, mock_load):
        _cache["municipalities"] = [
            {"name": "Playa", "province": "La Habana", "polygons": []},
            {"name": "Cerro", "province": "La Habana", "polygons": []},
        ]
        result = municipalities_map()
        assert result == {"La Habana": ["Cerro", "Playa"]}

    @patch("app.services.geo_lookup._load_layers")
    def test_fallback_static(self, mock_load):
        _cache["municipalities"] = []
        result = municipalities_map()
        assert "La Habana" in result
