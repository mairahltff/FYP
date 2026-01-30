import sys
sys.path.append("C:\\FYP")
from FYP_RAG.rag_query_ibm import tokenize, run_rag_query, LOCAL_INDEX, grounding_gate

# Prepare a minimal in-memory index for a dummy user
user_id = "test-user"
doc_text = (
    "The study reports that malaria cases increased by 12% in 2023 relative to 2022. "
    "Drivers include climatic variability and reduced intervention coverage."
)
LOCAL_INDEX[user_id] = [{
    "source": "who.pdf",
    "page": 1,
    "chunk": 1,
    "text": doc_text,
    "tokens": tokenize(doc_text),
}]

query = "What was the change in malaria cases in 2023?"
res = run_rag_query(query, user_id)
print("RAG result:", res)

# Grounding gate direct check
answer = "Malaria cases increased by 12% in 2023."
context = doc_text
print("Grounded:", grounding_gate(answer, context, query))
