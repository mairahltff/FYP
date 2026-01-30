import os
import re
import requests
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv
import PyPDF2

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
                     "You are a strict academic research assistant. "
                     "Use ONLY the provided context to answer. If the required information is not fully present in the context, respond exactly: 'Insufficient information in provided context.' "
                     "Answer ONLY what is asked — do not add background, definitions, speculation, projections, or unrelated statistics. "
                     "Write ONE concise academic paragraph (2–3 sentences maximum) in neutral tone. "
                     "Do NOT invent facts. Do NOT paraphrase beyond the context. Do NOT include dates outside the question’s timeframe. "
                     "Do NOT include citations, references, section numbers, or bullet points."
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
    docs = LOCAL_INDEX.get(user_id, [])

    scored = []
    for d in docs:
        score = len(q_tokens & d["tokens"]) / max(len(q_tokens), 1)
        if score > 0.1:
            scored.append((score, d))

    if not scored:
        return {
            "answer": "No relevant information found in the uploaded document.",
            "confidence": "Low (0.00)",
            "sources": [],
        }

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    context = " ".join(d["text"] for _, d in top)[:6000]

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
    }
