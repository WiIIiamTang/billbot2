import os
from dotenv import load_dotenv

load_dotenv()
PORT = os.getenv("PORT", 5000)
print("Waitress...")
os.system(f"waitress-serve --port={PORT} flaskapp:app")
