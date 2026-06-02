import secrets


def generate_session_code(*, max_attempts: int = 10) -> str:
    from game.models import GameSession

    for _ in range(max_attempts):
        code = f"{secrets.randbelow(10000):04d}"
        if not GameSession.objects.filter(code=code).exists():
            return code
    raise RuntimeError(
        f"could not generate unique session code in {max_attempts} attempts"
    )
