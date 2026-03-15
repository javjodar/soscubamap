from app.services.category_rules import is_other_type_allowed


class TestIsOtherTypeAllowed:
    def test_clean_text(self):
        assert is_other_type_allowed("Servicio comunitario") is True

    def test_represor(self):
        assert is_other_type_allowed("represor del barrio") is False

    def test_chivato(self):
        assert is_other_type_allowed("es un chivato") is False

    def test_informante(self):
        assert is_other_type_allowed("informante conocido") is False

    def test_delator(self):
        assert is_other_type_allowed("delator de vecinos") is False

    def test_dse(self):
        assert is_other_type_allowed("agente de la dse") is False

    def test_dgi(self):
        assert is_other_type_allowed("trabaja para la dgi") is False

    def test_empty(self):
        assert is_other_type_allowed("") is True

    def test_none(self):
        assert is_other_type_allowed(None) is True
