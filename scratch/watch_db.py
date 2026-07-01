import json
import time
import os

db_path = "/home/ubuntu/qrp/crypto-backtester/research_engine/outputs/experiment_registry.db"
if os.path.exists(db_path):
    print("Watching registry...")
    last_mtime = os.path.getmtime(db_path)
    for i in range(15):
        time.sleep(2)
        mtime = os.path.getmtime(db_path)
        if mtime != last_mtime:
            last_mtime = mtime
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                experiments = data.get("experiments", [])
                last_inserted = [e.get("experiment_id") for e in experiments[-5:]]
                print(f"Update detected at {time.strftime('%H:%M:%S')}: last={last_inserted}, total={len(experiments)}")
else:
    print("DB_NOT_FOUND")
