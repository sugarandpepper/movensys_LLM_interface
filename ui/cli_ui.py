"""Simple UI client that runs in its own terminal and sends commands to the server.

This UI automatically uses the `MobileRobot_Sequence` template.

Connection flow (UI -> Server -> UI):
- The UI forms a JSON payload containing `template_id`, `command`, and `meta`.
- It POSTs that payload to the server endpoint `/run_command`.
- The server responds with JSON (e.g. {"status":"ok","output":{...}}) and
  the UI prints the response for the user.

Example payload sent by `send_command`:
{
  "template_id": "MobileRobot_Sequence",
  "command": "move forward 5m; turn left",
  "meta": {}
}
"""
import requests
import json
import os

# Base server URL (can be overridden with MCP_SERVER_URL env var)
BASE = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")

# NOTE: UI does not need to know or send the template. The server will
# default to `MobileRobot_Sequence` if no `template_id` is provided. This
# keeps the UI decoupled from template management.


def send_command(command: str, meta: dict = None):
    """Send a command to the server and print the response.

    - Builds the JSON payload with `template_id`, `command`, and `meta`.
    - POSTs to the server `/run_command` endpoint.
    - Prints the server HTTP status and parsed JSON (or raw text on parse error).
    """
    url = f"{BASE}/run_command"
    # Payload: only send the user `command` and optional `meta`.
    # Server will select the template (defaulting to MobileRobot_Sequence).
    payload = {"command": command, "meta": meta or {}}
    # This is the network call that connects UI -> Server
    r = requests.post(url, json=payload, timeout=30)
    try:
        # Server should return JSON; pretty-print parsed object for readability
        out = r.json()
        print(r.status_code)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except Exception:
        # Fall back to printing raw text if JSON parsing fails
        print(r.status_code, r.text)


def repl():
    """Read-eval-print loop for user to type commands.

    The REPL prompts only for `command` (and optional `meta` JSON). It then
    calls `send_command` which performs the HTTP POST and prints the response.
    """
    print("MCP UI — enter 'quit' to exit")
    print("Using server default template: MobileRobot_Sequence")
    while True:
        cmd = input("command> ")
        if not cmd:
            continue
        if cmd.strip() == "quit":
            break
        meta_raw = input("meta JSON (optional)> ")
        meta = None
        if meta_raw.strip():
            try:
                meta = json.loads(meta_raw)
            except Exception as e:
                print("invalid meta JSON:", e)
                continue
        # Sends the command to server and prints server response
        send_command(cmd, meta)


if __name__ == "__main__":
    repl()
