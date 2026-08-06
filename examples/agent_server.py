"""Run the QuantMind agent API server."""

import os
import sys

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uvicorn.run("quantmind.api:app", host="0.0.0.0", port=port, reload=False)
