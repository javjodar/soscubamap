import pytest
from app.services.content_quality import validate_title, validate_description


class TestValidateTitle:
    def test_valid_title(self):
        ok, msg = validate_title("Detención arbitraria en Centro Habana")
        assert ok is True
        assert msg == ""

    def test_sigla_number(self):
        ok, _ = validate_title("UM 2104")
        assert ok is True

    def test_acronym(self):
        ok, _ = validate_title("PNR")
        assert ok is True

    def test_empty(self):
        ok, msg = validate_title("")
        assert ok is False
        assert "obligatorio" in msg

    def test_none(self):
        ok, msg = validate_title(None)
        assert ok is False

    def test_single_word(self):
        ok, msg = validate_title("Protesta")
        assert ok is False
        assert "2 palabras" in msg

    def test_too_short(self):
        ok, msg = validate_title("Ab cd")
        assert ok is False
        assert "corto" in msg

    def test_repeated_chars(self):
        ok, msg = validate_title("aaaaa bbbbb")
        assert ok is False
        assert "repeticiones" in msg

    def test_low_vowel_ratio(self):
        ok, msg = validate_title("xzxzxz trtrtrt")
        assert ok is False
        assert "palabras reales" in msg


class TestValidateDescription:
    def test_valid_description(self):
        text = "Fue detenido un joven en la esquina de la calle principal sin motivo aparente"
        ok, msg = validate_description(text)
        assert ok is True
        assert msg == ""

    def test_empty(self):
        ok, msg = validate_description("")
        assert ok is False
        assert "obligatoria" in msg

    def test_too_few_words(self):
        ok, msg = validate_description("Solo tres palabras aquí nada más ya")
        assert ok is False

    def test_none(self):
        ok, msg = validate_description(None)
        assert ok is False

    def test_repeated_chars(self):
        ok, msg = validate_description("Esto tiene aaaaaaaaa muchos caracteres repetidos en la oración completa aquí")
        assert ok is False
        assert "repeticiones" in msg

    def test_low_letter_ratio(self):
        ok, msg = validate_description("aa bb cc dd ee ff gg hh 111 222 333 444 555 666 777 888 999")
        assert ok is False
        assert "incompleta" in msg

    def test_repeated_words(self):
        ok, msg = validate_description("hola hola hola hola hola hola hola hola hola hola")
        assert ok is False
        assert "repite" in msg
