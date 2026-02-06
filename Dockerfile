# Python 3.12-slimをベースイメージとして使用
FROM python:3.12-slim

# 環境変数の設定
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8080

# 作業ディレクトリの設定
WORKDIR /app

# 依存パッケージのインストール
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルのコピーとインストール
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトファイルのコピー
COPY . /app/

# 静的ファイルの集約（デプロイ時またはコンテナ起動時に実行可能）
# RUN python manage.py collectstatic --noinput

# コンテナ起動コマンド（Gunicornを使用）
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 EDI_MP.wsgi:application
