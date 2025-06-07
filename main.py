import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- FastAPI App Setup ---

# Get the directory of the current file to locate the agent and static folders
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "static")

# Check if running in a Cloud Run environment to set the DB path
IS_CLOUD_RUN = 'K_SERVICE' in os.environ
DB_PATH = "/tmp/sessions.db" if IS_CLOUD_RUN else "./sessions.db"
SESSION_DB_URL = f"sqlite:///{DB_PATH}"

print(f"--- Using Database at: {SESSION_DB_URL} ---")

# Use ADK's helper to create a FastAPI app.
app: FastAPI = get_fast_api_app(
    agents_dir=ROOT_DIR,
    session_db_url=SESSION_DB_URL,
    allow_origins=["*"], # Allow all origins for simplicity
    web=True  # <--- THIS IS THE FIX. Explicitly enable serving web content.
)

# Mount the 'static' directory to serve our index.html and script.js
# This is handled automatically by get_fast_api_app when web=True,
# but adding it explicitly doesn't hurt and makes it clear.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")