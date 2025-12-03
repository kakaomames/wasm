# Dockerfile
FROM python:3.11-slim

# 必要なAPTパッケージのインストール (Rust, C/C++ ビルドツール、Supervisor)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    wget \
    # clang/lld (wasmターゲットに使用可能)
    clang lld \
    supervisor \
    # 後でクリーンアップ
    && rm -rf /var/lib/apt/lists/*

# --- 🎯 Rust環境のセットアップ ---
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o rustup-init.sh && \
    sh rustup-init.sh -y --profile minimal --default-toolchain stable && \
    rm rustup-init.sh
ENV PATH="/root/.cargo/bin:${PATH}"
RUN rustup target add wasm32-unknown-unknown

# ... Flask/RQ依存関係のインストール ...
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードとSupervisor設定のコピー
COPY . /app/
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8080

# サーバー起動コマンドを変更: Supervisorを起動し、GunicornとRQ Workerの両方を管理させる
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
