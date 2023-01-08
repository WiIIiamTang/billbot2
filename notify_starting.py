import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


r = requests.post(
    os.getenv("KOI_POSTCHECK_URL"),
    json={"time_started": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    headers={
        "Authorization": "Bearer " + os.getenv("KOI_AUTH_TOKEN"),
        "Content-Type": "application/json",
    },
)
print("[NOTIFIER]", r.status_code, r.content)
