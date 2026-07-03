import os
from dotenv import load_dotenv

load_dotenv()

WDA_URL = os.getenv("WDA_URL", "http://localhost:8100")
BUNDLE_ID = "com.snapchat.Snapchat"
LOW_BATTERY_THRESHOLD = 20
STATE_FILE = "state/progress.json"
