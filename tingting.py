import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

url = os.getenv("LIVEKIT_URL")
key = os.getenv("LIVEKIT_API_KEY")
secret = os.getenv("LIVEKIT_API_SECRET")

print("URL:", url)
print("KEY:", repr(key))
print("SECRET set:", bool(secret), "len:", len(secret) if secret else 0)
