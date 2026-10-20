# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy WAYPOINT_VAR=/var/waypoint
RUN pip install --no-cache-dir uv==0.12.5 && useradd --create-home --uid 10001 waypoint
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY agent agent
COPY app app
COPY config config
COPY data data
COPY mock_webank mock_webank
COPY rules rules
COPY sim sim
COPY skills skills
COPY tools tools
COPY --from=web /src/web/dist web/dist
RUN mkdir -p /var/waypoint && chown waypoint /var/waypoint
USER waypoint
EXPOSE 8000
CMD [".venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
