import os
from typing import Dict, Any

# Minimal LangChain pipeline wrapper that delegates to existing RAG functions
from langchain_core.runnables import RunnableLambda

from FYP_RAG.rag_query_ibm import run_rag_query, ingest_local_document, ingest_document_docling


def build_pipeline(user_id: str, prefer_docling: bool = True):
    def ingest(payload: Dict[str, Any]):
        path = payload.get("filepath")
        if not path:
            raise ValueError("filepath required for ingestion")
        if prefer_docling:
            ingest_document_docling(user_id, path)
        else:
            ingest_local_document(user_id, path)
        return {"status": "ingested", "filepath": path}

    def answer(payload: Dict[str, Any]):
        question = payload.get("question")
        if not question:
            raise ValueError("question required")
        return run_rag_query(question, user_id)

    # Compose ingest and answer as independent runnables
    return {
        "ingest": RunnableLambda(ingest),
        "answer": RunnableLambda(answer),
    }
