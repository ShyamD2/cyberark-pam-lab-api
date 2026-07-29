import os

# Must be set before app.main is imported: the write key is resolved at import time.
os.environ.setdefault("PAM_LAB_API_KEY", "lab-demo-key")
