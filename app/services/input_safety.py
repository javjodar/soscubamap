import re


_PATTERNS = [
    (re.compile(r"<\s*script", re.IGNORECASE), "script"),
    (re.compile(r"javascript:", re.IGNORECASE), "js-protocol"),
    (re.compile(r"<\s*iframe", re.IGNORECASE), "iframe"),
    (re.compile(r"<\s*svg", re.IGNORECASE), "svg"),
    (re.compile(r"onerror\s*=|onload\s*=", re.IGNORECASE), "inline-handler"),
    (re.compile(r"\bunion\s+select\b", re.IGNORECASE), "union-select"),
    (re.compile(r"\bselect\b\s+.+\bfrom\b", re.IGNORECASE), "select-from"),
    (re.compile(r"\bdrop\s+table\b", re.IGNORECASE), "drop-table"),
    (re.compile(r"\binsert\s+into\b", re.IGNORECASE), "insert-into"),
    (re.compile(r"\bupdate\b\s+.+\bset\b", re.IGNORECASE), "update-set"),
    (re.compile(r"\bpg_sleep\b|\bsleep\s*\(|\bwaitfor\s+delay\b", re.IGNORECASE), "sleep"),
    (re.compile(r"\bbenchmark\s*\(", re.IGNORECASE), "benchmark"),
    (re.compile(r"\bnslookup\b|\bping\b|\bcurl\b|\bwget\b", re.IGNORECASE), "rce"),
    (re.compile(r"\$\{|\{\{|<%", re.IGNORECASE), "template"),
    (re.compile(r"/etc/|/proc/|c:\\windows|win\.ini|/bin/", re.IGNORECASE), "path"),
    (re.compile(r"bxss\.me", re.IGNORECASE), "bxss"),
    (re.compile(r"%00|\x00", re.IGNORECASE), "nullbyte"),
]


def is_malicious(value: str) -> bool:
    if not value:
        return False
    for pattern, _label in _PATTERNS:
        if pattern.search(value):
            return True
    return False


def has_malicious_input(values) -> bool:
    for value in values:
        if not value:
            continue
        if is_malicious(str(value)):
            return True
    return False
