# =============================================================================
# run.py — Starts the development server
#
# Usage: python run.py
#
# load_dotenv() runs FIRST so ANTHROPIC_API_KEY is available before any
# module imports. reload=True auto-restarts when you edit a file.
# =============================================================================

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
