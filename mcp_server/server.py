"""MCP server module

This module exposes a single POST endpoint `/run_command` which accepts a JSON
payload with `template_id`, `command`, and optional `meta` metadata.

Flow (UI -> Server -> UI):
- UI (see `ui/cli_ui.py`) constructs a payload and POSTs to `/run_command`.
- Server loads the template file `templates/{template_id}.json` (defaults to
  `MobileRobot_Sequence` if not provided).
- If the template declares an MCP operation (e.g. `secure_sum`), the server
  calls `mcp_server.runner.perform_mcp_operation` to obtain `mcp_results` and
  injects them into `meta`.
- The server then calls `mcp_server.llm_client.generate_output` to produce the
  final structured output matching the template. The LLM client may be a
  real LLM (if `OPENAI_API_KEY` set) or a mock for offline development.
- The server returns JSON like: {"status":"ok","output":{...}}.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
from pathlib import Path
from typing import Dict, Any, Optional

from . import runner, llm_client


app = FastAPI()

# Templates directory (repo-level)
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


class ExecuteRequest(BaseModel):
    # `template_id` optional — if omitted, server will use default template
    template_id: Optional[str] = None
    # `command` is the user-typed free-form string from UI
    command: str
    # `meta` carries runtime parameters (e.g., values for secure_sum)
    meta: Dict[str, Any] = {}


@app.post("/run_command")
async def run_command(req: ExecuteRequest):
    """Handle a command from the UI and return a structured template output.

    Key connection points (for clarity):
    - UI -> request payload (see `ui/cli_ui.send_command`).
    - Template loading: server reads templates/{template_id}.json.
    - MCP runner: server may call `runner.perform_mcp_operation` to compute
      any server-side results and attach them into `meta["mcp_results"]`.
    - LLM generation: `llm_client.generate_output(command, template, meta)`
      produces the final structured output returned to the UI.
    """
    # Choose template, defaulting to MobileRobot_Sequence
    template_id = req.template_id or "MobileRobot_Sequence"
    template_path = TEMPLATE_DIR / f"{template_id}.json"
    if not template_path.exists():
        # UI receives 404 with this detail if template missing
        raise HTTPException(status_code=404, detail="template not found")

    # Load the JSON template that defines inputs/operation/output
    tpl = json.loads(template_path.read_text())
    op = tpl.get("operation", {})

    # Quick test behavior for `llm_sequence` templates: echo command back
    # to UI so a developer can verify round-trip without calling an LLM.
    if op.get("type") == "llm_sequence":
        # Response shape: {"status":"ok","output": {"sequence": <str>} }
        return {"status": "ok", "output": {"sequence": req.command}}

    # If template declares an MCP operation, run the runner and attach results
    meta = dict(req.meta or {})
    if op.get("type"):
        try:
            mcp_res = runner.perform_mcp_operation(op.get("type"), tpl.get("inputs", {}), meta)
            # Attach runner results for the LLM to consume when generating output
            meta["mcp_results"] = mcp_res
        except Exception as e:
            # UI will receive 500 with this detail
            raise HTTPException(status_code=500, detail=f"MCP error: {e}")

    # Call the LLM client (or mock) to produce the final output
    try:
        out = llm_client.generate_output(req.command, tpl, meta)
        return {"status": "ok", "output": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")
