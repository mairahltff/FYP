import os
import json
import sqlite3
import mimetypes
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account

# RAG engine
from FYP_RAG.rag_query_ibm import run_rag_query, ingest_local_document

load_dotenv()

app = Flask(__name__)
CORS(app)

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
                timestamp DATETIME
            )
        """)

# -----------------------------
# Cloud Storage (Firebase/GCS)
# -----------------------------
def _get_gcs_client():
    """Create a Google Cloud Storage client.
    Prefer credentials from GCP_SERVICE_ACCOUNT_JSON env if provided; otherwise default.
    """
    try:
        creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
        if creds_json:
            credentials = service_account.Credentials.from_service_account_info(json.loads(creds_json))
            return storage.Client(credentials=credentials)
        # Fallback to default credentials (will work locally if configured)
        return storage.Client()
    except Exception:
        return None

def upload_to_gcs(user_id: str, local_path: str, filename: str):
    """Upload a local file to GCS under uploads/{user_id}/{filename}.
    Returns the gs:// URI on success, else None.
    """
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        return None
    client = _get_gcs_client()
    if client is None:
        return None
    try:
        bucket = client.bucket(bucket_name)
        blob_path = f"uploads/{user_id}/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        blob.content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        blob.patch()
        return f"gs://{bucket_name}/{blob_path}"
    except Exception as e:
        app.logger.exception("GCS upload failed")
        return None

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload_docs", methods=["POST"])
def upload_docs():
    if "file" not in request.files:
        return jsonify(success=False, message="No file uploaded"), 400

    file = request.files["file"]
    user_id = request.form.get("user_id", "guest")

    if file.filename == "":
        return jsonify(success=False, message="Empty filename"), 400

    filename = secure_filename(file.filename)
    user_dir = os.path.join(UPLOAD_FOLDER, user_id)
    os.makedirs(user_dir, exist_ok=True)

    path = os.path.join(user_dir, filename)
    file.save(path)

    # Optional: Upload to cloud storage for persistence on Heroku
    cloud_uri = upload_to_gcs(user_id, path, filename)

    try:
        ingest_local_document(user_id, path)
        return jsonify(
            success=True,
            message="Successfully uploaded document",
            cloud_uri=cloud_uri
        )
    except Exception as e:
        app.logger.exception("Upload / ingest failed")
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

        # Log for FYP evaluation
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
                    datetime.now(),
                )
            )

        # 🔑 IMPORTANT: return RAW DATA ONLY (no HTML)
        return jsonify(
            success=True,
            answer=result["answer"],
            confidence=result["confidence"],
            sources=result["sources"],
        )

    except Exception as e:
        app.logger.exception("RAG query failed")
        return jsonify(
            success=False,
            answer="Internal error during RAG synthesis",
            error=str(e),
        ), 500


@app.route("/history", methods=["GET"])
def history():
    """Return past conversations for the given user_id.
    Does not touch RAG; reads from existing SQLite logs.
    """
    user_id = request.args.get("user_id", "guest")
    try:
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

        history = [
            {
                "id": r["id"],
                "query": r["query"],
                "answer": r["answer"],
                "confidence": r["confidence"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]
        return jsonify(success=True, history=history)
    except Exception as e:
        app.logger.exception("Fetch history failed")
        return jsonify(success=False, error=str(e)), 500


@app.route("/history/delete", methods=["POST"])
def history_delete():
    """Delete a single history item by id for the given user."""
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    user_id = data.get("user_id", "guest")

    if not item_id:
        return jsonify(success=False, message="Missing id"), 400

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "DELETE FROM query_logs WHERE id = ? AND user_id = ?",
                (item_id, user_id),
            )
        return jsonify(success=True, deleted=cur.rowcount)
    except Exception as e:
        app.logger.exception("Delete history item failed")
        return jsonify(success=False, error=str(e)), 500


@app.route("/history/clear", methods=["POST"])
def history_clear():
    """Delete all history items for the given user."""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "guest")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "DELETE FROM query_logs WHERE user_id = ?",
                (user_id,),
            )
        return jsonify(success=True, deleted=cur.rowcount)
    except Exception as e:
        app.logger.exception("Clear history failed")
        return jsonify(success=False, error=str(e)), 500


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5001))
    print(f"🔥 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
