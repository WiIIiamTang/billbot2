import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


r = requests.post(
    os.environ.get("KOI_POSTCHECK_URL"),
    data={"time_started": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    headers={"Authorization": "Bearer " + os.environ.get("KOI_AUTH_TOKEN")},
)
print(r.status_code, r.content)
