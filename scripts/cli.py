import requests
import json
import sys

BASE = "http://127.0.0.1:8000"


def run_command(command, meta=None):
    body = {"template_id": "MobileRobot_Sequence", "command": command, "meta": meta or {}}
    r = requests.post(f"{BASE}/run_command", json=body)
    print(r.status_code, r.text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python cli.py '<command>' '{"values":[1,2]}'")
    else:
        cmd = sys.argv[1]
        meta = None
        if len(sys.argv) > 2:
            try:
                meta = json.loads(sys.argv[2])
            except Exception:
                meta = None
        run_command(cmd, meta)
