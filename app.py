import os
import sqlite3
import time
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
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

# 25 MB upload cap (kept for local use)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# -----------------------------
# Paths & config
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "database.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------------
# RAG engine imports
# -----------------------------
from FYP_RAG.rag_query_ibm import run_rag_query
# NOTE: ingestion is disabled on Heroku safely

# -----------------------------
# Database init (CRITICAL FIX)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS perf_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                kind TEXT,
                ref TEXT,
                duration_ms INTEGER,
                success INTEGER,
                timestamp TEXT
            )
        """)

# ✅ MUST run at import time for Heroku
init_db()

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# Upload (DISABLED FOR HEROKU)
# -----------------------------
@app.route("/upload_docs", methods=["POST"])
def upload_docs():
    return jsonify(
        success=False,
        message="Document upload is disabled on the deployed demo."
    ), 200


# -----------------------------
# RAG Query (HARDENED)
# -----------------------------
@app.route("/query_rag", methods=["POST"])
def query_rag():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    user_id = data.get("user_id", "guest")

    if not query:
        return jsonify(success=False, answer="Empty query"), 400

    try:
        start = time.perf_counter()
        result = run_rag_query(query, user_id)

        # SAFETY: no documents / empty RAG state
        if not result or "answer" not in result:
            return jsonify(
                success=True,
                answer="No documents have been ingested yet.",
                confidence=None,
                sources=[]
            ), 200

        duration_ms = int((time.perf_counter() - start) * 1000)

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
                    result.get("answer"),
                    str(result.get("confidence")),
                    datetime.now().isoformat(timespec="seconds"),
                )
            )

        return jsonify(
            success=True,
            answer=result.get("answer"),
            confidence=result.get("confidence"),
            sources=result.get("sources", []),
            duration_ms=duration_ms,
        )

    except Exception as e:
        return jsonify(
            success=False,
            answer="Internal error during RAG synthesis",
            error=str(e),
        ), 500


# -----------------------------
# History
# -----------------------------
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
# Errors
# -----------------------------
@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    return jsonify(success=False, message="File too large. Max 25 MB."), 413
