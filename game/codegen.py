import secrets


def generate_session_code(*, max_attempts: int = 10) -> str:
    """Return a unique 4-digit session code as a zero-padded string.

    Uniqueness is best-effort: there is a TOCTOU race between the
    `.exists()` check and any subsequent `GameSession.objects.create()`
    in the caller. Two concurrent hosts can both pass the check on the
    same code; the second `create()` will then raise `IntegrityError`
    from the unique constraint on `GameSession.code`. Callers must wrap
    `generate_session_code()` + `create()` and retry on `IntegrityError`.

    Raises `RuntimeError` if every attempt collides with an existing row.
    """
    from game.models import GameSession

    for _ in range(max_attempts):
        code = f"{secrets.randbelow(10000):04d}"
        if not GameSession.objects.filter(code=code).exists():
            return code
    raise RuntimeError(
        f"could not generate unique session code in {max_attempts} attempts"
    )
