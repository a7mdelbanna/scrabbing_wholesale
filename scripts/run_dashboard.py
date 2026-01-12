"""Run the dashboard locally for development."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    print("Starting dashboard at http://localhost:8080")
    print("Press Ctrl+C to stop")
    uvicorn.run(
        "src.dashboard.app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=["src"],
    )
