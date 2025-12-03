# app.py
from flask import Flask, request, jsonify, render_template_string
import os
import uuid
import redis
from rq import Queue
from worker import rust_build_task, DEFAULT_RUST_TOML, c_build_task

# Redis接続設定 (Renderの環境変数から取得)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
print(f"REDIS_URL:{REDIS_URL}") # 隊長の指示に従い、値の決定時にprintします

# Flask App
app = Flask(__name__)

# Redisに接続し、RQのキューを初期化
redis_conn = redis.from_url(REDIS_URL)
print(f"redis_conn:{redis_conn}")
queue = Queue(connection=redis_conn)
print(f"queue:{queue}")

# --- API Routes ---

@app.route('/')
def home():
    """ルートはシンプルな情報とロゴを含むHTMLを返します。"""
    # 隊員の指示に基づき、HTMLのmetaタグを充実させます
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta name="description" content="Gemini programming隊 WASMビルドサーバー">
    <meta name="author" content="Gemini programming隊 隊長">
    <meta property="og:title" content="WASM Build Server">
    <meta property="og:description" content="Rust/C++ to WASM compilation service.">
    <meta property="og:image" content="{os.getenv('LOGO_URL', 'https://kakaomames.github.io/rei/logo.png')}">
    <title>WASM Server</title>
</head>
<body>
    <h1>🚀 WASMビルドサーバー稼働中</h1>
    <p>Render単一コンテナ内でGunicornとRQ Workerが稼働しています。</p>
    <h2>エンドポイント</h2>
    <ul>
        <li><code>POST /rust</code>: Rustコードをビルド</li>
        <li><code>GET /status?taskid=ID</code>: ビルドステータスをポーリング</li>
    </ul>
</body>
</html>
"""
    return render_template_string(html_content)

@app.route('/status')
def status_check():
    """タスクIDに基づき、進捗と結果をJSONで返します（ポーリング用）。"""
    task_id = request.args.get('taskid')
    print(f"task_id:{task_id}")

    if not task_id:
        return jsonify({"error": "taskidが必要です。例: /status?taskid=YOUR_ID"}), 400

    job = queue.fetch_job(task_id)
    
    if job is None:
        return jsonify({"status": "error", "message": f"タスクID '{task_id}' が見つかりません。"})
    
    job_status = job.get_status()
    print(f"job_status:{job_status}")
    
    if job_status in ['queued', 'started']:
        # 進行中のため 202 Accepted を返す
        message = "ビルド進行中または待機中です。" if job_status == 'started' else "キューで待機中です。"
        return jsonify({"taskid": task_id, "status": job_status, "message": message}), 202
    
    elif job_status == 'finished':
        result = job.result
        
        # ★★★ 修正箇所: 結果が None や無効な場合のガードを追加 ★★★
        if result is None:
             # タスクは完了したが、結果データがRedisから取得できない
            return jsonify({
                "taskid": task_id, 
                "status": "error", 
                "message": "タスクは完了しましたが、結果データ（job.result）がRedisから見つかりません。"
            }), 500
        # ★★★ 修正終了 ★★★

        if result and result.get('status') == 'completed':
            # 完了時、隊員指定の形式でJSONを返す (200 OK)
            return jsonify({
                "taskid": task_id,
                "status": "completed",
                "message": result.get('message', 'ビルド成功'),
                "js_code": result.get('js_code'),        # JavaScriptスタブコード
                "wasm_base64": result.get('wasm_base64') # Base64エンコードWASM
            }), 200
        else:
            # ビルドタスク内でエラーが発生した場合 (500 Internal Server Error)
            return jsonify({
                "taskid": task_id, 
                "status": "failed", 
                "message": result.get('message', 'ビルド失敗'),
                "details": result.get('details', '詳細不明')
            }), 500
    
    else:
        # RQレベルのシステムエラー (500 Internal Server Error)
        return jsonify({"taskid": task_id, "status": "error", "message": "タスク実行中に予期せぬシステムエラーが発生しました。"}), 500


@app.route('/rust', methods=['POST'])
def submit_rust_build():
    """Rustのビルドタスクをキューに追加し、タスクIDを返します。"""
    data = request.json
    rs_code = data.get('rs')
    cargo_toml = data.get('toml', DEFAULT_RUST_TOML)

    if not rs_code:
        return jsonify({"error": "Rustソースコード (rs) が必要です。"}), 400

    build_id = str(uuid.uuid4())
    print(f"build_id:{build_id}")

    # バックグラウンドタスクをキューに追加
    job = queue.enqueue(
        rust_build_task, 
        build_id, 
        rs_code, 
        cargo_toml,
        job_timeout='300s' # 最大5分までビルドを許可
    )
    print(f"job:{job}")

    # タスクIDを即時返却 (200 OK)
    return jsonify({
        "taskid": job.id,
        "message": f"Rustビルドタスクを受理しました。ステータスは /status?taskid={job.id} で確認してください。"
    }), 200

@app.route('/c-c++', methods=['POST'])
def submit_c_build():
    """C/C++のビルドタスクをキューに追加します。"""
    data = request.json
    cpp_code = data.get('cpp')

    if not cpp_code:
        return jsonify({"error": "C/C++ソースコード (cpp) が必要です。"}), 400

    build_id = str(uuid.uuid4())
    print(f"build_id:{build_id}")

    # バックグラウンドタスクをキューに追加
    job = queue.enqueue(
        c_build_task, 
        build_id, 
        cpp_code, 
        job_timeout='300s'
    )
    print(f"job:{job}")
    
    # 実際には worker.py の c_build_task が未実装のため、エラーを返します
    return jsonify({"taskid": job.id, "message": "C/C++ ビルドタスクを受理しました。", "warning": "worker.pyのc_build_taskを実装してください。"}), 200
