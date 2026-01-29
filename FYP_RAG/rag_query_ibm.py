import os
import re
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List
import PyPDF2

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

LOCAL_INDEX: Dict[str, List[dict]] = {}


def tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


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
                chunks.append({
                    "source": filename,
                    "page": page_num,
                    "chunk": (i // 4) + 1,
                    "text": block,
                    "tokens": tokenize(block),
                })

    LOCAL_INDEX.setdefault(user_id, []).extend(chunks)


def get_iam_token():
    res = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "apikey": os.getenv("WATSONX_API_KEY"),
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        },
    )
    return res.json()["access_token"]


def call_granite(question: str, context: str) -> str:
    token = get_iam_token()
    url = f"{os.getenv('WATSONX_URL')}/ml/v1/text/generation?version=2023-05-29"

    prompt = (
        "You are a research assistant.\n"
        "Write ONE academic paragraph that directly answers the question.\n"
        "Use ONLY the provided context.\n"
        "DO NOT include references, citations, confidence scores, headings, or lists.\n"
        "DO NOT mention sources.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    payload = {
        "model_id": "ibm/granite-3-3-8b-instruct",
        "project_id": os.getenv("IBM_PROJECT_ID"),
        "input": prompt,
        "parameters": {
            "max_new_tokens": 400,
            "temperature": 0.2
        }
    }

    res = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=payload
    )

    if res.status_code != 200:
        raise RuntimeError(res.text)

    return res.json()["results"][0]["generated_text"].strip()


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

    context = " ".join(d["text"] for _, d in top)
    answer = call_granite(query, context)

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
