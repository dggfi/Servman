import asyncio
import traceback
import json
from asyncio.queues import Queue
from collections import defaultdict
from uuid import uuid4 as uuidv4
import websockets
from helpers import action, ServmanAgent
from typings import IParcel


class PingClient(ServmanAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # State
        self.ping_count = 0
        self.pong_count = 0
        self.complete = False

        self.identifier = f'my_heartbeat_{str(uuidv4())}'

    ### Actions
    @action()
    async def pong(self, parcel: IParcel, websocket, queue):
        self.pong_count += 1
        msg = parcel['data']['msg']
        print(msg)

    ### Events
    async def on_service_created(self, identifier, connection_id, websocket, queue):
        purpose = 'communicate'
        await self.new_proxy_connection(identifier, purpose)
        pending_future = self.new_wait_until_connected(purpose)
        await pending_future()

        proxy_connection_id = self._proxy_connection_ids[purpose]
        ping_parcel: IParcel = {
            'routing': 'service',
            'destination_id': proxy_connection_id,
            'action': 'ping'
        }
        ping_parcel = json.dumps(ping_parcel)

        queue = self._proxy_message_queues[purpose]
        ping_count = 0
        while ping_count < 10:
            await queue.put(ping_parcel)
            ping_count += 1
            await asyncio.sleep(1)
        self.complete = True

        kill_parcel: IParcel = {
            'routing': 'servman',
            'action': 'kill',
            'data': { 'secret': 'my_secret' }
        }
        kill_parcel = json.dumps(kill_parcel)
        await queue.put(kill_parcel)
        await asyncio.sleep(5)
        try:
            exit()
        except BaseException:
            pass

    ### Tasks
    async def on_connect(self, websocket, queue):
        """
            Immediately request a new Servman task on connection.
        """
        connection_id = self._primary_websocket.request_headers['connection_id']
        parcel: IParcel = {
            'routing': 'servman',
            'action': 'create_service',
            'data': {
                'args': [],
                'kwargs': {
                    'owner_id': self._agent_id,
                    'owner_connection_id': connection_id,
                    'identifier': self.identifier
                },
                'target': 'heartbeat',
                'options': {}
            }
        }

        await self._primary_message_queue.put(json.dumps(parcel))

    async def consume(self):
        await self.wait_until_connected()

        while not self.complete:
            packet = await self._primary_websocket.recv()
            parcel = json.loads(packet)
            callback = self._callbacks[parcel['action']]
            asyncio.create_task(callback(self, parcel, self._primary_websocket, self._primary_message_queue))    

    async def produce(self):
        await self.wait_until_connected()

        while not self.complete:
            await self._primary_websocket.send(await self._primary_message_queue.get())

    def get_tasks(self):
        return [
            self.connect,
            self.consume,
            self.produce
        ]

    async def do_work(self):
        tasks = self.get_tasks()
        await asyncio.gather(*tasks)
    
    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())