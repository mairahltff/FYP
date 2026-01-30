import os
import re
import requests
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv
import PyPDF2
import chromadb
from chromadb.errors import ChromaError
from chromadb.utils import embedding_functions
try:
    import docling
except Exception:
    docling = None

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

print("✅ WATSONX_API_KEY loaded:", bool(os.getenv("WATSONX_API_KEY")))
print("✅ IBM_PROJECT_ID loaded:", bool(os.getenv("IBM_PROJECT_ID")))
print("✅ WATSONX_URL:", os.getenv("WATSONX_URL"))


# In-memory index: user_id -> chunks
LOCAL_INDEX: Dict[str, List[dict]] = {}
STOPWORDS = {
    "the","a","an","and","or","but","if","then","than","that","this","those","these",
    "is","are","was","were","be","been","being","of","in","on","for","to","with","without",
    "by","as","at","from","it","its","their","there","here","such","can","may","might","should",
    "must","could","will","would","do","does","did","not","no","yes","about","into","within","between",
}


# -----------------------------
# Chroma setup + IBM Embeddings
# -----------------------------
def _get_vectorstore_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "vectorstore")


def get_chroma_collection(user_id: str):
    client = chromadb.PersistentClient(path=_get_vectorstore_path())
    # Use local sentence-transformers embeddings (offline-friendly)
    emb_model = os.getenv("SENTENCE_TRANSFORMER_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    emb_fn = None
    try:
        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=emb_model)
        print(f"✅ Using local embeddings: {emb_model}")
    except Exception as e:
        print("⚠️ SentenceTransformer embeddings unavailable; proceeding without embedding function:", e)
    return client.get_or_create_collection(
        name=f"user_{user_id}",
        metadata={"hnsw:space": "cosine"},
        embedding_function=emb_fn,
    )


# -----------------------------
# Utils
# -----------------------------
def tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


# -----------------------------
# Document ingestion
# -----------------------------
def ingest_local_document(user_id: str, filepath: str):
    filename = os.path.basename(filepath)
    chunks = []

    with open(filepath, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            if not text:
                continue

            sentences = re.split(r"(?<=[.!?])\s+", text)
            for i in range(0, len(sentences), 4):
                block = " ".join(sentences[i:i + 4])
                if not block.strip():
                    continue

                chunks.append({
                    "source": filename,
                    "page": page_num,
                    "chunk": (i // 4) + 1,
                    "text": block,
                    "tokens": tokenize(block),
                })

    LOCAL_INDEX.setdefault(user_id, []).extend(chunks)

    # Also add to Chroma for vector retrieval (best-effort; fall back if embeddings unavailable)
    try:
        col = get_chroma_collection(user_id)
        ids = []
        docs = []
        metas = []
        for c in chunks:
            ids.append(f"{filename}_p{c['page']}_c{c['chunk']}")
            docs.append(c["text"])
            metas.append({"source": filename, "page": c["page"], "chunk": c["chunk"]})
        if docs:
            col.add(ids=ids, documents=docs, metadatas=metas)
    except Exception as e:
        print("⚠️ Chroma ingest failed (falling back to LOCAL_INDEX only):", e)


# -----------------------------
# Docling ingestion (best-effort)
# -----------------------------
def ingest_document_docling(user_id: str, filepath: str):
    """
    Prefer Docling for robust parsing + chunking if available;
    fallback to PyPDF2-based ingestion otherwise.
    """
    if docling is None:
        print("ℹ️ Docling not available, using PyPDF2 ingestion.")
        return ingest_local_document(user_id, filepath)

    filename = os.path.basename(filepath)
    chunks = []
    try:
        # Docling API varies; attempt generic pipeline and fallback on error
        # Use docling.parse to extract text segments, if supported
        from docling_parse import Parser  # type: ignore
        parser = Parser()
        doc = parser.parse(filepath)
        texts = []
        try:
            # Collect paragraphs or segments (best-effort)
            texts = [seg.text for seg in getattr(doc, "segments", []) if getattr(seg, "text", "")]  # type: ignore
        except Exception:
            pass
        if not texts:
            # Fallback: use PyPDF2 path
            print("ℹ️ Docling parse returned no segments, falling back to PyPDF2.")
            return ingest_local_document(user_id, filepath)

        # Group texts into blocks of ~4 segments
        for i in range(0, len(texts), 4):
            block = clean_text(" ".join(texts[i:i+4]))
            if not block:
                continue
            chunks.append({
                "source": filename,
                "page": 0,
                "chunk": (i // 4) + 1,
                "text": block,
                "tokens": tokenize(block),
            })
    except Exception as e:
        print("⚠️ Docling ingestion failed, using PyPDF2:", e)
        return ingest_local_document(user_id, filepath)

    LOCAL_INDEX.setdefault(user_id, []).extend(chunks)

    # Sync into Chroma
    try:
        col = get_chroma_collection(user_id)
        ids = []
        docs = []
        metas = []
        for c in chunks:
            ids.append(f"{filename}_p{c['page']}_c{c['chunk']}")
            docs.append(c["text"])
            metas.append({"source": filename, "page": c["page"], "chunk": c["chunk"]})
        if docs:
            col.add(ids=ids, documents=docs, metadatas=metas)
    except Exception as e:
        print("⚠️ Chroma ingest failed (Docling path):", e)


# -----------------------------
# Watsonx / Granite
# -----------------------------
def get_iam_token():
    api_key = os.getenv("WATSONX_API_KEY")
    if not api_key:
        raise RuntimeError("Missing WATSONX_API_KEY")

    res = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "apikey": api_key,
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        },
        timeout=15
    )

    if res.status_code != 200:
        raise RuntimeError(f"IAM token failed: {res.text}")

    return res.json().get("access_token")


def call_granite(question: str, context: str) -> str:
    token = get_iam_token()

    url = os.getenv("WATSONX_URL")
    project_id = os.getenv("IBM_PROJECT_ID")
    if not url or not project_id:
        raise RuntimeError("Watsonx env vars missing")

    endpoint = f"{url}/ml/v1/text/chat?version=2024-02-15"

    payload = {
        "model_id": "ibm/granite-3-8b-instruct",
        "project_id": project_id,
        "messages": [
            {
                "role": "system",
                 "content": (
                     "You are an academic assistant. "
                     "Use only the provided context to answer. "
                     "If the context does not fully support the answer, reply exactly: 'Insufficient information in provided context.' "
                     "Answer only what is asked, in 1–3 complete sentences. "
                     "Do not add background, opinions, predictions, or unrelated details. "
                     "Do not invent facts or numbers; prefer wording from the context. "
                     "Respect any timeframe or scope stated in the question."
                 )
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion:\n{question}"
            }
        ],
        "parameters": {
            "temperature": 0.0,
            "top_p": 0.1,
            "max_new_tokens": 180
        }
    }

    res = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )

    # Handle quota / auth issues
    if res.status_code in (401, 403, 429):
        raise RuntimeError(f"Watsonx quota/auth error: {res.status_code}")

    if res.status_code != 200:
        raise RuntimeError(f"Watsonx error {res.status_code}: {res.text}")

    try:
        data = res.json()
    except Exception:
        raise RuntimeError(f"Non-JSON Watsonx response: {res.text}")

    # Support both schemas
    if "choices" in data:
        return data["choices"][0]["message"]["content"].strip()

    if "results" in data:
        return data["results"][0]["generated_text"].strip()

    raise RuntimeError(f"Unexpected Watsonx response: {data}")


# -----------------------------
# Grounding gate
# -----------------------------
def grounding_gate(answer: str, context: str, query: str) -> bool:
    """
    Returns True if the answer appears grounded in the provided context
    and query (i.e., uses mostly tokens present in them), otherwise False.
    """
    a_tokens = tokenize(answer) - STOPWORDS
    c_tokens = tokenize(context)
    q_tokens = tokenize(query)
    allowed = c_tokens | q_tokens

    if not a_tokens:
        return True

    unknown = a_tokens - allowed
    # If more than 30% of answer tokens are not found in context/query, flag as ungrounded
    return (len(unknown) / max(len(a_tokens), 1)) <= 0.30


# -----------------------------
# Extractive fallback
# -----------------------------
def extractive_fallback(top, q_tokens):
    sentences = []
    for _, d in top:
        txt = d.get("text") or ""
        if txt:
            sentences.extend(re.split(r"(?<=[.!?])\s+", txt))

    if not sentences:
        return top[0][1].get("text", "").strip()

    scored = []
    for s in sentences:
        overlap = len(tokenize(s) & q_tokens)
        if overlap > 0:
            scored.append((overlap, s))

    if not scored:
        return sentences[0].strip()

    scored.sort(key=lambda x: x[0], reverse=True)
    return " ".join(s for _, s in scored[:5]).strip()


# -----------------------------
# RAG query (MAIN)
# -----------------------------
def run_rag_query(query: str, user_id: str):
    q_tokens = tokenize(query)

    top = []
    context = ""
    retrieval_method = "fallback-token"
    # First try: Chroma similarity search
    try:
        col = get_chroma_collection(user_id)
        results = col.query(query_texts=[query], n_results=5, include=["documents", "metadatas", "distances"])
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        # Convert distances to similarity (cosine space)
        for doc, meta, dist in zip(docs, metas, dists):
            sim = 1.0 - float(dist)
            top.append((sim, {"text": doc, "source": meta.get("source"), "page": meta.get("page"), "chunk": meta.get("chunk")}))
        top.sort(key=lambda x: x[0], reverse=True)
        context = " ".join(d["text"] for _, d in top)[:6000]
        retrieval_method = "vector"
    except (ChromaError, Exception) as e:
        print("⚠️ Chroma query failed, falling back to token overlap:", e)
        # Fallback: token overlap over LOCAL_INDEX
        docs = LOCAL_INDEX.get(user_id, [])
        scored = []
        for d in docs:
            score = len(q_tokens & d["tokens"]) / max(len(q_tokens), 1)
            if score > 0.1:
                scored.append((score, d))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:5]
            context = " ".join(d["text"] for _, d in top)[:6000]

    if not top:
        return {
            "answer": "No relevant information found in the uploaded document.",
            "confidence": "Low (0.00)",
            "sources": [],
            "retrieval": retrieval_method,
        }

    try:
        answer = call_granite(query, context)
    except Exception as e:
        print("⚠️ Granite failed, using fallback:", e)
        answer = extractive_fallback(top, q_tokens)

    # Enforce grounding to avoid hallucinations
    if answer.strip().lower() == "insufficient information in provided context." or not grounding_gate(answer, context, query):
        # Prefer extractive fallback from retrieved chunks for strict grounding
        answer = extractive_fallback(top, q_tokens)

    avg = sum(s for s, _ in top) / len(top)
    label = "High" if avg >= 0.6 else "Medium"

    sources = []
    for _, d in top[:3]:
        src = f"{d['source']} — Page {d['page']} (Chunk {d['chunk']})"
        if src not in sources:
            sources.append(src)

    return {
        "answer": answer,
        "confidence": f"{label} ({avg:.2f})",
        "sources": sources,
        "retrieval": retrieval_method,
    }
