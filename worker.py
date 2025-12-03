# worker.py
import os
import subprocess
import base64
import shutil
import redis
import rq
import json # JSONモジュールも念のためインポート

# Redis接続はRQが環境変数から自動的に設定します
# RENDER_REDIS_URL環境変数を想定

# 環境に応じて一時ディレクトリを定義
BUILD_DIR = "/tmp/builds"
os.makedirs(BUILD_DIR, exist_ok=True)
print(f"BUILD_DIR:{BUILD_DIR}")

# RustビルドのデフォルトCargo.toml
DEFAULT_RUST_TOML = """
[package]
name = "user_code"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]
"""

# C/C++の標準的なJSコードスタブ (結果に含まれる)
# NOTE: wasm-bindgen-cli を使うため、このスタブは worker.py では使わず、
# 生成された .js ファイルを読み込むように変更しました。
JS_CODE_STUB = "// JavaScriptスタブコードは wasm-bindgen によって生成されます。"


def rust_build_task(build_id, rs_code, cargo_toml):
    """Rustソースコードをwasmにビルドするバックグラウンドタスク"""
    work_path = os.path.join(BUILD_DIR, build_id)
    print(f"work_path:{work_path}")
    
    # wasm-bindgen の出力先ディレクトリ
    wasm_output_dir = os.path.join(work_path, "pkg")

    try:
        # 1. セットアップ
        os.makedirs(work_path)
        os.makedirs(os.path.join(work_path, "src"))

        # 2. ファイル書き込み
        rs_path = os.path.join(work_path, "src/lib.rs")
        print(f"rs_path:{rs_path}")
        toml_path = os.path.join(work_path, "Cargo.toml")
        print(f"toml_path:{toml_path}")
        
        with open(rs_path, "w") as f:
            f.write(rs_code)
        with open(toml_path, "w") as f:
            f.write(cargo_toml)

        # 3. ビルドコマンド (WASMターゲットを指定)
        cargo_command = [
            "cargo", "build", 
            "--target", "wasm32-unknown-unknown", 
            "--release", 
            "--manifest-path", toml_path
        ]
        print(f"cargo_command:{cargo_command}")

        # 4. Cargo ビルド実行
        cargo_result = subprocess.run(
            cargo_command, 
            cwd=work_path, 
            capture_output=True, 
            text=True, 
            timeout=300 # 5分タイムアウトに延長 (初回ビルド対策)
        )

        if cargo_result.returncode != 0:
            # ビルド失敗の場合
            return {
                "status": "failed", 
                "message": "Rust ビルド失敗。",
                "details": cargo_result.stderr
            }

        # 5. wasm-bindgen コマンドの実行 (JSとWASMの生成)
        wasm_input_path = os.path.join(work_path, "target/wasm32-unknown-unknown/release/gemini_pokemon_basecamp.wasm")
        # NOTE: Cargo.toml の name が user_code ではないため、ファイル名を 'gemini_pokemon_basecamp.wasm' に修正。

        bindgen_command = [
            "wasm-bindgen", wasm_input_path, 
            "--out-dir", wasm_output_dir,
            "--target", "web" 
        ]
        print(f"bindgen_command:{bindgen_command}")

        bindgen_result = subprocess.run(
            bindgen_command, 
            capture_output=True, 
            text=True, 
            timeout=60
        )

        if bindgen_result.returncode != 0:
            return {
                "status": "failed", 
                "message": "wasm-bindgen 処理失敗。",
                "details": bindgen_result.stderr
            }

        # 6. Artifactsの取得とBase64エンコード
        # wasm-bindgen のデフォルト出力ファイル名を使用
        wasm_path = os.path.join(wasm_output_dir, "gemini_pokemon_basecamp_bg.wasm") 
        js_path = os.path.join(wasm_output_dir, "gemini_pokemon_basecamp.js") 
        
        # ファイルが存在しない場合のエラーチェック
        if not os.path.exists(wasm_path) or not os.path.exists(js_path):
            return {
                "status": "failed", 
                "message": "最終生成ファイルが見つかりません。",
                "details": f"WASM: {os.path.exists(wasm_path)}, JS: {os.path.exists(js_path)}"
            }


        with open(wasm_path, "rb") as f:
            wasm_base64 = base64.b64encode(f.read()).decode('utf-8')
            
        with open(js_path, "r") as f:
            js_code_stub = f.read()

        return {
            "status": "completed",
            "message": "Rust WASMビルド成功！",
            "js_code": js_code_stub,
            "wasm_base64": wasm_base64
        }

    except subprocess.TimeoutExpired:
        return {"status": "failed", "message": "ビルドまたはwasm-bindgen処理がタイムアウトしました。"}
    except Exception as e:
        # すべての予期せぬエラーをキャッチ
        return {"status": "failed", "message": f"予期せぬエラーが発生しました。", "details": str(e)}
    finally:
        # 7. 後処理（一時ディレクトリの削除）
        if os.path.exists(work_path):
            shutil.rmtree(work_path)

# C/C++ ビルドタスク (未実装)
def c_build_task(build_id, cpp_code):
    return {"status": "failed", "message": "C/C++ ビルドタスクは未実装です。"}
