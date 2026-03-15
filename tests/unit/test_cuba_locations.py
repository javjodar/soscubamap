from app.services.cuba_locations import PROVINCES, MUNICIPALITIES


class TestCubaLocations:
    def test_provinces_not_empty(self):
        assert len(PROVINCES) > 0

    def test_known_provinces(self):
        assert "La Habana" in PROVINCES
        assert "Santiago de Cuba" in PROVINCES

    def test_municipality_count(self):
        assert len(MUNICIPALITIES) == len(PROVINCES)

    def test_municipalities_mapped(self):
        assert "Playa" in MUNICIPALITIES["La Habana"]
        assert "Bayamo" in MUNICIPALITIES["Granma"]
