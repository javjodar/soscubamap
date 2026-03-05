import hashlib


def get_voter_hash(current_user, request, secret_key: str) -> str:
    if current_user.is_authenticated:
        raw = f"user:{current_user.id}"
    else:
        ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or ""
        ua = request.headers.get("User-Agent", "")
        raw = f"anon:{ip}|{ua}"
    return hashlib.sha256(f"{secret_key}:{raw}".encode("utf-8")).hexdigest()
