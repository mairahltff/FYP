import sys, os
sys.path.append("C:\\FYP")
from FYP_RAG.rag_query_ibm import get_chroma_collection, tokenize, run_rag_query, LOCAL_INDEX

user_id = "chroma-user"
os.environ["WATSONX_EMBED_MODEL"] = "ibm/granite-embedding-107m-multilingual"
col = get_chroma_collection(user_id)

# Create one simple document in vector store and local index
text = (
    "The report states intervention coverage decreased in 2023, "
    "which correlated with a 12% increase in malaria cases compared to 2022."
)
try:
    col.add(ids=["doc1"], documents=[text], metadatas=[{"source": "who.pdf", "page": 1, "chunk": 1}])
except Exception as e:
    print("⚠️ Chroma add failed (will still test fallback):", e)
LOCAL_INDEX[user_id] = [{"source": "who.pdf", "page": 1, "chunk": 1, "text": text, "tokens": tokenize(text)}]

query = "How did malaria cases change in 2023?"
res = run_rag_query(query, user_id)
print("Chroma RAG result:", res)
