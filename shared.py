# logging
from datetime import datetime

def log(level: str, msg : str):
    now = datetime.now()
    timestamp = now.strftime("%Y.%m.%d %H:%M:%S")
    print(f"[{timestamp}][{level}]: {msg}")