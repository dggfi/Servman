import multiprocessing
import asyncio
from asyncio import Queue

from asyncio.futures import Future
import websockets
import traceback, logging
import json
from json.decoder import JSONDecodeError
from path import Path
from collections import defaultdict
from .typings import IConnectionConfig, IParcel
from .service import Service
from typing import Callable, Coroutine


class ServiceManager:
    """
       A task scheduler and communication proxy between clients
       and scheduled tasks. Server-like. 
    """
    def __init__(self, config_path: str, default_service: Callable or Coroutine or None=None):
        if default_service:
            self._default_service = default_service

        # Config
        config_path = Path(config_path)

        if not config_path.exists():
            print(f"Error: File {config_path} does not exist.")
            exit()

        config = ''

        try:
            config = json.loads(config_path.read_text())
        except JSONDecodeError:
            print(f"The JSON in {config_path} is not formatted correctly.")
            exit()

        self.config: IConnectionConfig = config

        # Actions
        actions = {
            'create_service': self.create_service
        }

        def return_bad_action(): return self.bad_action
        self.actions = defaultdict(return_bad_action, actions)

        # Routes
        routes = {
            'servman': self.open_here,
            'client': self.route_to_client,
            'service': self.route_to_service
        }

        def return_bad_route(): return self.bad_route
        self.routes = defaultdict(return_bad_route, routes)

        # Websockets
        self.host = config['host']
        self.port = config['port']
        self.server = websockets.serve(
            self.handle_websockets,
            self.host,
            self.port,
            max_queue=2048,
            max_size=None,
            origins=[]
        )

        # Connections
        self.connections = {} # origin_id: service
        self.allowed_origins = set([
            'discord_client',
            'web_client',
            'service'
        ])

        # Sockets
        self.registered_sockets = {}

        # Messageing
        self.outgoing_parcels = Queue() # A websocket message

        # Misc.
        self.t_ping = None
        self.logger = logging.getLogger("websockets.server")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(logging.StreamHandler())
    
    # Websockets
    async def handle_websocket(self, websocket):
        await self.register_websocket(websocket)
        try:
            async for message in websocket:
                parcel: IParcel = json.loads(message)
                await self.routes[parcel['routing']](parcel)
        except Exception as e:
            print(f"Error in ServiceManger.handle_websocket: {e}")
            traceback.print_exc()
        finally:
            await self.unregister_websocket(websocket)
    
    async def register_websocket(self, websocket):
        origin_id = ''
        connection_id = ''
        try:
            origin_id = websocket.request_headers['origin']
            connection_id = websocket.request_headers['connection_id']
        except KeyError:
            print("WARNING: Websocket missing critical Register field in request header.")
            return
        
        if origin_id not in self.allowed_origins:
            print(f"WARNING: Websocket made request with invalid origin {origin_id}.")
            return
        
        self.connections[connection_id] =  websocket

    async def unregister_websocket(self, websocket):
        try:
            connection_id = websocket.request_headers['connection_id']
        except KeyError:
            print(f"Warning: Websocket missing origin_id in the request header")
            return
        finally:
            self.connections.pop(connection_id, None)
            await websocket.close()
    
    # Actions -- Error
    async def bad_action(self, parcel: IParcel):
        print(f"Error: Got a bad action! '{parcel['action']}'' in parcel {parcel}")
    
    async def bad_route(self, parcel: IParcel):
        print(f"ERROR: Got a bad route! '{parcel['route']}' in parcel {parcel}")
    
    # Actions -- Parcels
    async def open_here(self, parcel: IParcel):
        await self.actions[parcel['action']](parcel)
    
    async def route_to_other(self, parcel: IParcel):
        connection = self.connections.get(parcel['destination_id'], None)
        if connection:
            await connection.send(json.dumps(parcel))
        else:
            print(f"ERROR: Connection with ID {parcel['destination_id']} not found!")
            await self.unregister_websocket(self.connections[parcel['destination_id']])
    
    # Actions -- Services
    async def create_service(self, parcel: IParcel, target=None):
        if not target:
            target = self._default_service

        # construct params
        args = tuple()
        connection_ids = {
            'client_connection_id': parcel['origin_id'],
            'service_connection_id': parcel['destination_id']
        }
        meta = parcel['data']['meta']
        connection_config = {
            'host': self.config['host'],
            'port': self.config['port']
        }
        kwargs = {
            'connection_ids': connection_ids,
            'meta': meta,
            'connection_config': connection_config,
        }
        params = {
            'args': args,
            'kwargs': kwargs
        }

        service = Service(target, params)
        self.connections[connection_ids['service_connection_id']] = service
        service.run()

    def run(self):
        multiprocessing.set_start_method("spawn")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.server)