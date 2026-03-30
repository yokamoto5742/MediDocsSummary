# Stage 1: フロントエンドビルド
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
COPY app/templates/ /app/app/templates/
RUN npm run build

# Stage 2: Python本番イメージ
FROM python:3.13-slim
WORKDIR /app

# uvのインストール
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 設定ファイルとソースを先にコピー
COPY pyproject.toml uv.lock ./
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY --from=frontend-builder /app/app/static/dist app/static/dist

# システム環境にインストールするための設定
ENV UV_PROJECT_ENVIRONMENT="/usr/local"
# uv sync から --system を削除
RUN uv sync --frozen --no-dev --no-install-project

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]