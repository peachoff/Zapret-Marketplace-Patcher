import uuid
import os

DEVICE_FILE = os.path.expanduser("~/.zmp_device_id")

def get_device_id() -> str:
    if os.path.exists(DEVICE_FILE):
        with open(DEVICE_FILE, "r") as f:
            return f.read().strip()

    device_id = str(uuid.uuid4())
    os.makedirs(os.path.dirname(DEVICE_FILE), exist_ok=True)
    with open(DEVICE_FILE, "w") as f:
        f.write(device_id)
    return device_id
