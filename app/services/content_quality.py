import re


_RE_SIGLA_NUM = re.compile(r"^[A-Z]{2,5}[-\s]?\d{1,6}$", re.IGNORECASE)
_RE_ACRONYM = re.compile(r"^[A-Z]{3,5}$")
_RE_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
_RE_LETTER = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
_RE_VOWEL = re.compile(r"[AEIOUÁÉÍÓÚÜaeiouáéíóúü]")


def _has_repeated_chars(value: str, limit: int) -> bool:
    if not value:
        return False
    count = 1
    prev = value[0]
    for ch in value[1:]:
        if ch == prev:
            count += 1
            if count >= limit:
                return True
        else:
            prev = ch
            count = 1
    return False


def _letter_ratio(value: str) -> float:
    letters = len(_RE_LETTER.findall(value))
    compact = len(re.sub(r"\s+", "", value))
    return (letters / compact) if compact else 0.0


def _vowel_ratio(value: str) -> float:
    letters = len(_RE_LETTER.findall(value))
    vowels = len(_RE_VOWEL.findall(value))
    return (vowels / letters) if letters else 0.0


def validate_title(title: str) -> tuple[bool, str]:
    value = (title or "").strip()
    if not value:
        return False, "El título es obligatorio."

    if _RE_SIGLA_NUM.match(value):
        return True, ""
    if _RE_ACRONYM.match(value):
        return True, ""

    words = _RE_WORD.findall(value)
    if len(words) < 2:
        return False, "El título debe tener al menos 2 palabras o una sigla con número (ej: UM 2104)."

    if len(value) < 6:
        return False, "El título es demasiado corto."

    if _has_repeated_chars(value, 4):
        return False, "El título contiene demasiadas repeticiones."

    if _vowel_ratio(value) < 0.2:
        return False, "El título no parece válido. Agrega palabras reales."

    return True, ""


def validate_description(description: str) -> tuple[bool, str]:
    value = (description or "").strip()
    if not value:
        return False, "La descripción es obligatoria."

    words = _RE_WORD.findall(value)
    if len(words) < 8:
        return False, "La descripción debe tener al menos 8 palabras."

    if _has_repeated_chars(value, 6):
        return False, "La descripción contiene demasiadas repeticiones."

    if _letter_ratio(value) < 0.6:
        return False, "La descripción parece incompleta o inválida."

    unique_ratio = len(set(w.lower() for w in words)) / max(len(words), 1)
    if unique_ratio < 0.3:
        return False, "La descripción repite demasiadas palabras."

    return True, ""
