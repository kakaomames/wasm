# worker.py
import os
import subprocess
import base64
import shutil
import uuid
import redis
import rq

# Redis接続はRQが環境変数から自動的に設定します
# RENDER_REDIS_URL環境変数を想定

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

# C/C++の標準的なJSコードスタブ
JS_CODE_STUB = """
// WASM instantiation code stub
async function loadWasm(base64Data) {
    const bytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
    const module = await WebAssembly.compile(bytes);
    const instance = new WebAssembly.Instance(module);
    console.log('WASM loaded successfully!', instance.exports);
    return instance;
}
"""

def rust_build_task(build_id, rs_code, cargo_toml):
    """Rustソースコードをwasmにビルドするバックグラウンドタスク"""
    work_path = os.path.join(BUILD_DIR, build_id)
    print(f"work_path:{work_path}")
    
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

        # 3. ビルドコマンド
        command = [
            "cargo", "build", 
            "--target", "wasm32-unknown-unknown", 
            "--release", 
            "--manifest-path", toml_path
        ]
        print(f"command:{command}")

        # 4. 実行
        result = subprocess.run(
            command, 
            cwd=work_path, 
            capture_output=True, 
            text=True, 
            timeout=180
        )

        if result.returncode != 0:
            return {
                "status": "failed", 
                "message": "Rust ビルド失敗。",
                "details": result.stderr
            }

        # 5. Artifactsの取得とBase64エンコード
        wasm_path = os.path.join(work_path, "target/wasm32-unknown-unknown/release/user_code.wasm") 
        print(f"wasm_path:{wasm_path}")
        
        with open(wasm_path, "rb") as f:
            wasm_data = f.read()
            wasm_base64 = base64.b64encode(wasm_data).decode('utf-8')
        # 出力が多いので一部のみ表示
        print(f"wasm_base64[:20]:{wasm_base64[:20]}")

        return {
            "status": "completed",
            "message": "Rust ビルド成功！",
            "js_code": JS_CODE_STUB, # 隊員のリクエスト通り、JSコードスタブを含めます
            "wasm_base64": wasm_base64
        }

    except subprocess.TimeoutExpired:
        return {"status": "failed", "message": "ビルドがタイムアウトしました。"}
    except Exception as e:
        return {"status": "failed", "message": f"予期せぬエラー: {str(e)}"}
    finally:
        # 6. 後処理（一時ディレクトリの削除）
        if os.path.exists(work_path):
            shutil.rmtree(work_path)

# C/C++ ビルドタスクも同様に定義が必要です (今回はRustをメインに実装)
def c_build_task(build_id, cpp_code):
    # C/C++用のビルドロジックをここに記述
    return {"status": "failed", "message": "C/C++ ビルドタスクは未実装です。"}
