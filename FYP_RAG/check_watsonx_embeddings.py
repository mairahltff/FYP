import os
import requests
from pathlib import Path

# Reuse IAM token logic by implementing inline to keep script independent

def get_iam_token(api_key: str) -> str:
    res = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "apikey": api_key,
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        },
        timeout=20,
    )
    res.raise_for_status()
    return res.json().get("access_token")


def list_models(url: str, token: str):
    # Try models catalog endpoint
    endpoint = f"{url}/ml/v1/models?version=2024-02-15"
    r = requests.get(endpoint, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code == 200:
        return r.json()
    # Fallback: try foundation models endpoint (SDK-like REST)
    endpoint2 = f"{url}/ml/v1/foundation_models?version=2024-02-15"
    r2 = requests.get(endpoint2, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r2.status_code == 200:
        return r2.json()
    raise RuntimeError(f"Failed to list models: {r.status_code} {r.text} / {r2.status_code} {r2.text}")


def main():
    url = os.getenv("WATSONX_URL")
    project_id = os.getenv("IBM_PROJECT_ID")
    api_key = os.getenv("WATSONX_API_KEY")
    if not (url and project_id and api_key):
        print("Missing env vars: WATSONX_URL, IBM_PROJECT_ID, WATSONX_API_KEY")
        return

    token = get_iam_token(api_key)
    data = list_models(url, token)

    # Try to locate Granite embedding models
    candidates = []
    items = []
    if isinstance(data, dict):
        # Normalize possible schemas
        items = data.get("resources") or data.get("models") or data.get("results") or []
    else:
        items = data

    for m in items:
        mid = m.get("model_id") or m.get("id") or m.get("name")
        name = m.get("name") or m.get("display_name") or mid
        tags = m.get("tags") or m.get("task_ids") or m.get("tasks") or []
        provider = m.get("provider") or m.get("origin") or ""
        if mid and ("embedding" in str(tags).lower() or "text-embeddings" in str(tags).lower()):
            if "granite" in str(mid).lower() or "granite" in str(name).lower():
                candidates.append((mid, name))

    print("Granite embedding candidates in this project/region:")
    for mid, name in candidates:
        print(f"- {mid} | {name}")

    if not candidates:
        print("No Granite embedding models listed via catalog endpoints. You may need to enable the offering in your project or use the exact model id provided by IBM console.")
        return

    # Probe each candidate with a tiny embedding request
    test_text = ["hello world"]
    for mid, name in candidates:
        ep = f"{url}/ml/v1/text/embeddings?version=2024-02-15"
        payload = {"model_id": mid, "project_id": project_id, "inputs": test_text}
        r = requests.post(ep, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=30)
        if r.status_code == 200:
            print(f"SUPPORTED: {mid} ({name})")
        else:
            print(f"UNSUPPORTED ({r.status_code}): {mid} ({name}) -> {r.text[:200]}")


if __name__ == "__main__":
    main()
