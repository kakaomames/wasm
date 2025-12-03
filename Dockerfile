# Dockerfile
FROM python:3.11-slim

# 必要なAPTパッケージのインストール (Rust, C/C++ ビルドツール、Supervisor)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    wget \
    clang lld \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# --- 🎯 Rust環境のセットアップ ---
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o rustup-init.sh && \
    sh rustup-init.sh -y --profile minimal --default-toolchain stable && \
    rm rustup-init.sh
    
# PATH変数を設定 (Rustツールチェーンへのアクセスを確保)
ENV PATH="/root/.cargo/bin:${PATH}"

# WASMターゲットの追加
RUN rustup target add wasm32-unknown-unknown

# 🎯 WASM-BINDGEN-CLIのインストール (ここが重要！)
RUN cargo install wasm-bindgen-cli

# --- Python環境とAppコードのセットアップ ---
WORKDIR /app
# requirements.txtを先にコピーしてインストールし、キャッシュを有効活用
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードとSupervisor設定のコピー
COPY . /app/
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8080

# サーバー起動コマンドを変更: Supervisorを起動
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
