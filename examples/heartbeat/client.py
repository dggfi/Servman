import asyncio
import traceback
import json
from asyncio.queues import Queue
from collections import defaultdict
from uuid import uuid4 as uuidv4
import websockets
from typings import IParcel
from helpers import ServmanAgent

class PingClient:
    def __init__(self):
        self.agent_id = str(uuidv4())

        # State
        self.connected = False
        self.websocket = None
        self.ping_count = 0
        self.pong_count = 0

        # Collections
        self.service_agent_id = None
        self.message_queue = Queue()
        actions = {
            'pong': self.pong,
            'finalize': self.finalize
        }
        def return_bad_action(): return self.bad_action
        self.actions = defaultdict(return_bad_action, actions)

        # Misc.
        self.loop = asyncio.get_event_loop()


    ### Actions
    async def pong(self, parcel: IParcel):
        self.pong_count += 1
        msg = parcel['data']['msg']
        # print(msg)


    async def finalize(self, parcel: IParcel):
        self.service_agent_id = parcel['data']['service_agent_id']

        new_parcel: IParcel = {
            'routing': 'service',
            'destination_id': self.service_agent_id,
            'action': 'ping'
        }

        new_parcel = json.dumps(new_parcel)

        ping_count = 0
        while ping_count < 10:
            await self.websocket.send(new_parcel)
            ping_count += 1
            await asyncio.sleep(1)


    ### Tasks
    async def connect(self):
        port = 8000
        host = 'localhost'
        connection_uri = f"ws://{host}:{port}"

        extra_headers = [
            ('agent', 'client'),
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
        self.connected = True


    ### Tasks
    async def wait_until_ready(self):
        while not self.connected:
            await asyncio.sleep(0.1)
        # print(f"Client {self.agent_id} ready.")


    async def start_service(self):
        await self.wait_until_ready()

        parcel: IParcel = {
            'routing': 'servman',
            'action': 'create_service',
            'data': {
                'args': [],
                'kwargs': {
                    'owner_id': self.agent_id
                },
                'target': 'heartbeat',
                'hash': 'my_hash'
            }
        }

        await self.message_queue.put(json.dumps(parcel))


    async def consume(self):
        await self.wait_until_ready()
        while self.pong_count < 10:
            packet = await self.websocket.recv()
            parcel = json.loads(packet)
            asyncio.create_task(self.actions[parcel['action']](parcel))
    

    async def produce(self):
        await self.wait_until_ready()
        while self.pong_count < 10:
            await self.websocket.send(await self.message_queue.get())

    def get_tasks(self):
        return [
            self.connect,
            self.start_service,
            self.consume,
            self.produce
        ]

    async def do_work(self):
        tasks = self.get_tasks()
        await asyncio.gather(*tasks)
    
    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())