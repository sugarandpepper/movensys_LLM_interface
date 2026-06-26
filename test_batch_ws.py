import asyncio
import json
import websockets

TEST_MESSAGES = [
    "(1, 1) 좌표로 이동해줘",
    "(10,10) 좌표로 이동해줘",
    "(2.5, 7.1) 좌표로 이동해줘",
    "(3,4)",
    "C로 이동해줘",
    "이건 그냥 대화야: 안녕?",
]

async def run_test():
    uri = 'ws://localhost:8000/ws'
    async with websockets.connect(uri) as ws:
        for msg_text in TEST_MESSAGES:
            print('\n---')
            print('SEND:', msg_text)
            await ws.send(json.dumps({"type": "message", "text": msg_text}))
            finished = False
            while not finished:
                res = await ws.recv()
                data = json.loads(res)
                print('RECV:', json.dumps(data, ensure_ascii=False))
                t = data.get('type')
                if t == 'commands':
                    # 자동으로 confirm
                    print('AUTO: confirming commands')
                    await ws.send(json.dumps({"type": "confirm"}))
                elif t == 'result' or t == 'chat' or t == 'error' or t == 'cancelled':
                    finished = True

asyncio.run(run_test())
