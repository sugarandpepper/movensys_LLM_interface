import asyncio
import json
import websockets

async def main():
    uri = "ws://localhost:8000/ws"
    try:
        async with websockets.connect(uri) as ws:
            msg = {"type": "message", "text": "(3, 4) 좌표로 이동해줘"}
            print('SENDING:', msg)
            await ws.send(json.dumps(msg))
            while True:
                res = await ws.recv()
                print('RECV:', res)
                data = json.loads(res)
                if data.get('type') == 'result':
                    break
    except Exception as e:
        print('ERROR:', e)

if __name__ == '__main__':
    asyncio.run(main())
