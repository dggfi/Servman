import asyncio
import traceback
import json
from asyncio.queues import Queue
from collections import defaultdict
from uuid import uuid4 as uuidv4
import websockets
from typings import IParcel


class PongService:
    def __init__(self, *args, **kwargs):
        self.agent_id = str(uuidv4())
        self.owner_agent_id = kwargs['owner_id']

        # State
        self.ping_count = 0
        self.connected = False
        self.websocket = None

        # Collections
        self.message_queue = Queue()
        actions = {
            'ping': self.ping,
        }
        def return_bad_action(): return self.bad_action
        self.actions = defaultdict(return_bad_action, actions)

        # Misc.
        self.loop = asyncio.get_event_loop()


    ### Actions
    async def ping(self, parcel: IParcel):
        self.ping_count += 1

        new_parcel: IParcel = {
            'routing': 'client',
            'destination_id': self.owner_agent_id,
            'action': 'pong',
            'data': {
                'msg': f"PONG! ({self.ping_count} pings and counting from {self.agent_id}!)"
            }
        }

        await self.websocket.send(json.dumps(new_parcel))


    ### Tasks
    async def connect(self):
        port = 8000
        host = 'localhost'
        connection_uri = f"ws://{host}:{port}"

        extra_headers = [
            ('agent', 'service'),
            ('agent_id', self.agent_id)
        ]

        try:
            self.websocket = await websockets.connect(
                connection_uri,
                extra_headers=extra_headers
            )
        except Exception as e:
            print(f"Service with ID {self.agent_id} failed to connect!")
            print(e)
            traceback.print_exc()
            exit()
        
        print(f"Success! Service with  ID {self.agent_id} connected!")
        self.connected = True


    async def wait_until_ready(self):
        while not self.connected:
            await asyncio.sleep(0.1)
    

    async def finalize(self):
        await self.wait_until_ready()
        
        parcel: IParcel = {
            'routing': 'client',
            'destination_id': self.owner_agent_id,
            'action': 'finalize',
            'data': {
                'service_agent_id': self.agent_id
            }
        }

        await self.websocket.send(json.dumps(parcel))


    async def receive(self):
        await self.wait_until_ready()
        while self.ping_count < 10:
            packet = await self.websocket.recv()
            parcel = json.loads(packet)
            asyncio.create_task(self.actions[parcel['action']](parcel))
    

    async def send(self):
        await self.wait_until_ready()
        while self.ping_count < 10:
            await self.websocket.send(await self.message_queue.get())

    async def do_work(self):
        tasks = [
            self.connect(),
            self.finalize(),
            self.receive(),
            self.send()
        ]
        await asyncio.gather(*tasks)

    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())


def pong_service(*args, **kwargs):
    print("Running a pong service.")
    pong_service = PongService(*args, **kwargs)
    pong_service.run()