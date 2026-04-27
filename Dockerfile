# Python 3.12-slimをベースイメージとして使用
FROM python:3.12-slim

# 環境変数の設定
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# 作業ディレクトリの設定
WORKDIR /app

# 依存パッケージのインストール
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルのコピーとインストール
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトファイルのコピー
COPY . /app/

# エントリポイントスクリプトの設定
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# メディアディレクトリの作成
RUN mkdir -p /app/media

# 静的ファイルの集約（ビルド時は.envが利用できないためダミーの環境変数を設定）
RUN SECRET_KEY=build-dummy-key ALLOWED_HOSTS=localhost DEBUG=False \
    python manage.py collectstatic --noinput --settings=EDI_MP.settings

# エントリポイント
ENTRYPOINT ["/app/entrypoint.sh"]

# コンテナ起動コマンド（Gunicornを使用）
CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 EDI_MP.wsgi:application"]
