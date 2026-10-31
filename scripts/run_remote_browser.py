"""Mac/local terminal launcher. Private values stay in process memory."""
from getpass import getpass
import os

import uvicorn

from axle_hackathon.remote_client import DEMO_BASE_URL, load_client_config


if __name__ == "__main__":
    for name, label in (("MODEL_API_KEY", "Existing Meta model API key"),
                        ("AXLE_DEMO_TOKEN", "Existing local browser password"),
                        ("AXLE_REMOTE_API_TOKEN", "Existing private remote Axle token")):
        if not os.environ.get(name):
            os.environ[name] = getpass(label + " (hidden): ")
        if not os.environ[name].strip():
            raise SystemExit("Required private configuration is missing")
    os.environ["AXLE_BROWSER_EVALUATOR"] = "remote"
    os.environ["AXLE_REMOTE_BASE_URL"] = DEMO_BASE_URL
    load_client_config()
    print("Open http://127.0.0.1:8000; user carrier; password is your local demo token.")
    print("Synthetic-only. Each extraction/evaluation uses Meta credits. No automatic retry.")
    uvicorn.run("axle_hackathon.app:app", host="127.0.0.1", port=8000, access_log=False)
