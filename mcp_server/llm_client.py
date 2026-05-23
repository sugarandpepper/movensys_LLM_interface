import os
import json
import requests
from typing import Dict, Any


def generate_output(command: str, template: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured output for a given command and template using an LLM or mock.

    Behavior:
    - If OPENAI_API_KEY is set, calls OpenAI ChatCompletions (via REST) to generate JSON.
    - Otherwise returns a mocked deterministic result for offline testing.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    system = (
        "You are an assistant that reads a user command and a JSON template,"
        " and must produce a JSON object that matches the template's output fields."
    )
    user_msg = {
        "command": command,
        "template": template,
        "meta": meta,
    }

    if api_key:
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_msg)}
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        text = body["choices"][0]["message"]["content"].strip()
        try:
            return json.loads(text)
        except Exception:
            return {"_raw": text}
    else:
        op = template.get("operation", {})
        if op.get("type") == "secure_sum":
            mcp_res = meta.get("mcp_results") or {}
            return {"sum": mcp_res.get("sum", None), "_mocked": True}
        return {"result": "mocked-output", "_mocked": True}
