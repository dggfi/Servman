import asyncio
import traceback
import json
from asyncio.queues import Queue
from collections import defaultdict
from uuid import uuid4 as uuidv4
import websockets
from helpers import ServmanAgent, action
from typings import IParcel
from path import Path


class PongService(ServmanAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(connection_config=kwargs['connection_config'])

        # State
        self.ping_count = 0

        # Connection details
        # You will need this information to send parcels to the client
        self.owner_id = kwargs['owner_id']
        self.owner_connection_id = kwargs['owner_connection_id']
        self.identifier = kwargs['identifier']

    ### Actions
    @action()
    async def ping(self, parcel: IParcel, websocket, queue):
        self.ping_count += 1

        new_parcel: IParcel = {
            'routing': 'client',
            'destination_id': self.owner_connection_id,
            'action': 'pong',
            'data': {
                'msg': f"PONG! ({self.ping_count} pings and counting from {self._agent_id}!)"
            }
        }

        await websocket.send(json.dumps(new_parcel))
        if self.ping_count >= 10:
            await asyncio.sleep(3)
            try:
                exit()
            except BaseException:
                pass


    ### Tasks
    async def on_connect(self, websocket, queue):
        parcel: IParcel = {
            'routing': 'client',
            'destination_id': self.owner_connection_id,
            'action': 'catch_service_credentials',
            'data': {
                'identifier': self.identifier,
                'connection_id': websocket.request_headers['connection_id']
            }
        }

        await self._primary_websocket.send(json.dumps(parcel))

    async def consume(self):
        await self.wait_until_connected()
        while self.ping_count < 10:
            packet = await self._primary_websocket.recv()
            parcel = json.loads(packet)
            action = self._actions[parcel['action']]
            asyncio.create_task(action.callback(action.agent, parcel, self._primary_websocket, self._primary_message_queue))

    async def produce(self):
        await self.wait_until_connected()

        while self.ping_count < 10:
            await self._primary_websocket.send(await self._primary_message_queue.get())


def pong_service(*args, **kwargs):
    config_file = Path("conf/service_configuration.json")
    if not config_file.exists():
        print("Error: Connection config for service does not exist!")
        exit()
    connection_config = json.loads(config_file.read_text(encoding="utf-8"))
    kwargs["connection_config"] = connection_config

    pong_service = PongService(*args, **kwargs)
    pong_service.run()