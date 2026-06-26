# server.py
import json
import sys
import os
import asyncio
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

sys.path.append(os.path.join(os.path.dirname(__file__), 'model'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'ros2_ws', 'src'))

from chat import load_model, classify_input, general_chat, convert_to_commands, modify_commands, parse_commands
from ros2_bridge import send_to_robot_ros2, shutdown_ros

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

model, tokenizer = None, None

@app.on_event("startup")
async def startup():
    global model, tokenizer
    model, tokenizer = load_model()

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    commands = []
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                user_input = data.get("text", "").strip()
                if not user_input:
                    continue

                # 좌표 입력 감지: 먼저 좌표 패턴을 검사해서 좌표 명령으로 바로 처리
                coord_match = re.search(r'\((\d+\.?\d*),\s*(\d+\.?\d*)\)', user_input)
                if coord_match:
                    x, y = coord_match.group(1), coord_match.group(2)
                    cmd = f"navigate_to({x}, {y})"
                    await ws.send_json({"type": "executing"})
                    result = send_to_robot_ros2([cmd])
                    await ws.send_json({
                        "type": "result",
                        "success": result["success"],
                        "message": result["message"],
                        "executed": result.get("executed", []),
                        "status_report": result.get("status_report", "")
                    })
                    continue

                input_type = classify_input(user_input)

                if input_type == "chat":
                    reply = general_chat(user_input)
                    await ws.send_json({"type": "chat", "text": reply})

                else:
                    await ws.send_json({"type": "converting"})
                    commands = convert_to_commands(model, tokenizer, user_input)
                    if not commands:
                        await ws.send_json({"type": "error", "text": "명령어 변환에 실패했습니다."})
                    else:
                        await ws.send_json({"type": "commands", "commands": commands})

            elif msg_type == "confirm":
                await ws.send_json({"type": "executing"})
                result = send_to_robot_ros2(commands)
                await ws.send_json({
                    "type": "result",
                    "success": result["success"],
                    "message": result["message"],
                    "executed": result.get("executed", []),
                    "status_report": result.get("status_report", "")
                })

            elif msg_type == "modify":
                modify_text = data.get("text", "")
                await ws.send_json({"type": "converting"})
                modified = modify_commands(model, tokenizer, commands, modify_text)
                if modified:
                    commands = modified
                    await ws.send_json({"type": "commands", "commands": commands})
                else:
                    await ws.send_json({"type": "error", "text": "수정에 실패했습니다."})

            elif msg_type == "cancel":
                commands = []
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "quick_cmd":
                cmd = data.get("cmd", "")
                await ws.send_json({"type": "executing"})
                result = send_to_robot_ros2([cmd])
                await ws.send_json({
                    "type": "result",
                    "success": result["success"],
                    "message": result["message"],
                    "executed": result.get("executed", []),
                    "status_report": result.get("status_report", "")
                })

    except WebSocketDisconnect:
        shutdown_ros()
