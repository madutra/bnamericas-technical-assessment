# The upstream is not ours: this only packages it, nothing in upstream/ is changed.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app/upstream
COPY upstream/ ./
RUN uv sync --locked --no-dev

EXPOSE 8081
# `uv run upstream` binds to 127.0.0.1, which other containers cannot reach. The factory form calls the
# same create_app() but listens on every interface.
CMD [".venv/bin/uvicorn", "records_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
