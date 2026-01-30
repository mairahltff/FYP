import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# -----------------------------
# Load environment
# -----------------------------
load_dotenv()

# -----------------------------
# Flask app
# -----------------------------
app = Flask(__name__)
CORS(app)

# -----------------------------
# RAG engine
# -----------------------------
from FYP_RAG.rag_query_ibm import run_rag_query, ingest_local_document

# -----------------------------
# Paths & config
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "database.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------------
# Database
# -----------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                query TEXT,
                answer TEXT,
                confidence TEXT,
                timestamp TEXT
            )
        """)

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload_docs", methods=["POST"])
def upload_docs():
    file = request.files.get("file")
    user_id = request.form.get("user_id", "guest")

    if not file or file.filename == "":
        return jsonify(success=False, message="No file uploaded"), 400

    filename = secure_filename(file.filename)
    user_dir = os.path.join(UPLOAD_FOLDER, user_id)
    os.makedirs(user_dir, exist_ok=True)

    path = os.path.join(user_dir, filename)
    file.save(path)

    try:
        ingest_local_document(user_id, path)
        return jsonify(success=True, message="Successfully uploaded document")
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


@app.route("/query_rag", methods=["POST"])
def query_rag():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    user_id = data.get("user_id", "guest")

    if not query:
        return jsonify(success=False, answer="Empty query"), 400

    try:
        result = run_rag_query(query, user_id)

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO query_logs
                (user_id, query, answer, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    query,
                    result["answer"],
                    result["confidence"],
                    datetime.now().isoformat(timespec="seconds"),
                )
            )

        return jsonify(
            success=True,
            answer=result["answer"],
            confidence=result["confidence"],
            sources=result["sources"],
        )

    except Exception as e:
        return jsonify(
            success=False,
            answer="Internal error during RAG synthesis",
            error=str(e),
        ), 500


@app.route("/history", methods=["GET"])
def history():
    user_id = request.args.get("user_id", "guest")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, query, answer, confidence, timestamp
            FROM query_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (user_id,),
        ).fetchall()

    return jsonify(
        success=True,
        history=[dict(row) for row in rows]
    )


@app.route("/history/delete", methods=["POST"])
def history_delete():
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    user_id = data.get("user_id", "guest")

    if not item_id:
        return jsonify(success=False, message="Missing id"), 400

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM query_logs WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )

    return jsonify(success=True, deleted=cur.rowcount)


@app.route("/history/clear", methods=["POST"])
def history_clear():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "guest")

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM query_logs WHERE user_id = ?",
            (user_id,),
        )

    return jsonify(success=True, deleted=cur.rowcount)

# -----------------------------
# Main (CRITICAL FIX HERE)
# -----------------------------
if __name__ == "__main__":
    init_db()
    print("🔥 Flask running on port 5001")

    # 🚨 IMPORTANT:
    # use_reloader=False prevents Flask from running TWO processes
    # which was wiping your in-memory RAG index
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False,
        use_reloader=False
    )
