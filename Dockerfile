FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# 의존성만 먼저 설치해서 코드만 바뀌었을 때는 이 층을 캐시로 재사용
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn avengers_bank.main:app --host 0.0.0.0 --port 8000"]
