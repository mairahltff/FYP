import requests
import os

URL = "http://127.0.0.1:5001/upload_docs"
USER_ID = "e2e-user"
PDF_PATH = r"C:\FYP\uploads\e2e-user\vector_control_test.pdf"

if not os.path.exists(PDF_PATH):
    raise SystemExit(f"Missing file: {PDF_PATH}")

with open(PDF_PATH, "rb") as f:
    files = {"file": (os.path.basename(PDF_PATH), f, "application/pdf")}
    data = {"user_id": USER_ID}
    resp = requests.post(URL, files=files, data=data, timeout=30)
    print("Status:", resp.status_code)
    try:
        print("Body:", resp.json())
    except Exception:
        print("Body:", resp.text)
