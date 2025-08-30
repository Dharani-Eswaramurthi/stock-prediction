import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_HOST = os.getenv("BACKEND_HOST", "51.20.120.226")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
BACKEND_BASE_URL = f"https://{BACKEND_HOST}:{BACKEND_PORT}"

UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "")
# Redirect URI must match app settings in Upstox console
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", f"{BACKEND_BASE_URL}/auth/callback")

OPENAI_API_KEY = os.getenv("API_KEY_OPENAI", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501,http://localhost:3000").split(",")