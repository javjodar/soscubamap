import markdown as md
import bleach


ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
}


def render_markdown(text: str) -> str:
    raw = md.markdown(text or "", extensions=["extra", "sane_lists", "nl2br"])
    clean = bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    return clean
