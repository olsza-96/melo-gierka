FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./

RUN uv sync --frozen --no-dev

COPY . .

# DJANGO_DEBUG=True bypasses the SECRET_KEY guard for these build-time
# management commands. Runtime CMD inherits DEBUG=False from fly.toml [env]
# and the real DJANGO_SECRET_KEY from `fly secrets`.
RUN export DJANGO_DEBUG=True \
 && uv run python manage.py migrate --noinput \
 && uv run python manage.py seed_catalog \
 && uv run python manage.py collectstatic --noinput

EXPOSE 8080

CMD ["uv", "run", "gunicorn", "melo_gierka.wsgi", \
     "--workers", "1", "--threads", "4", \
     "--bind", "0.0.0.0:8080", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
