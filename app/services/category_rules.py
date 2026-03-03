import re


_OTHER_TYPE_BLOCKLIST = re.compile(
    r"\b("
    r"represor(?:es)?|"
    r"chivat[oa]s?|"
    r"informante(?:s)?|"
    r"delator(?:es)?|"
    r"seguridad\\s+del\\s+estado|"
    r"dse|dgi"
    r")\b",
    re.IGNORECASE,
)


def is_other_type_allowed(value: str) -> bool:
    if not value:
        return True
    return _OTHER_TYPE_BLOCKLIST.search(value) is None
