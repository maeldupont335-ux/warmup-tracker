import os
import json
import subprocess
from dotenv import load_dotenv

load_dotenv()


def _detect_udid() -> str:
    env = os.getenv("DEVICE_UDID", "auto")
    if env != "auto":
        return env
    try:
        r = subprocess.run(["tidevice", "list", "--json"],
                           capture_output=True, text=True, timeout=5)
        devices = json.loads(r.stdout)
        if devices:
            return devices[0].get("udid", "auto")
    except Exception:
        pass
    return "auto"


APPIUM_SERVER = os.getenv("APPIUM_SERVER", "http://localhost:4723")
BUNDLE_ID = "com.snapchat.Snapchat"

CAPS = {
    "platformName": "iOS",
    "platformVersion": "16.7",
    "deviceName": "iPhone X",
    "udid": _detect_udid(),
    "bundleId": BUNDLE_ID,
    "automationName": "XCUITest",
    "noReset": True,       # CRITIQUE : ne jamais déconnecter le compte
    "fullReset": False,
    "newCommandTimeout": 300,
    "wdaLaunchTimeout": 60000,
    "wdaConnectionTimeout": 60000,
}

SESSION_WINDOWS = {
    "morning": (8, 12),
    "evening": (18, 23),
}

LOW_BATTERY_THRESHOLD = 20
STATE_FILE = "state/progress.json"
