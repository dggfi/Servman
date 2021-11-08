import multiprocessing
import asyncio
import websockets
import traceback, logging
import json
from json.decoder import JSONDecodeError
from path import Path
from uuid import uuid4 as uuidv4
from collections import defaultdict
from typings import IConnectionConfig, IParcel
from service import Service, ServicePool
from typing import Any, Callable

class ServiceManager:
    """
       A task scheduler and communication proxy between clients
       and scheduled tasks. Server-like. 
    """
    def __init__(self, config_path: str):
        self.agent_id = str(uuidv4())

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
            'client': self.route_to_other,
            'service': self.route_to_other
        }

        def return_bad_route(): return self.bad_route
        self.routes = defaultdict(return_bad_route, routes)

        self.allowed_agents = set([
            'client',
            'service'
        ])

        # Websockets API
        self.host = config['host']
        self.port = config['port']
        self.connection_config = {
            'host': self.host,
            'port': self.port
        }

        # Collections
        self.agent_to_websocket = {} # agent_id: websocket
        self.agent_to_services = {} # agent_id: Service
        self.tasks = {} # str: Callable

        # Misc.
        self.t_ping = None
        self.logger = logging.getLogger("websockets.server")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(logging.StreamHandler())
    

    ### Websocket
    async def register_websocket(self, websocket):
        print("Registering a new websocket connection.")
        agent = ''
        agent_id = ''
        try:
            agent = websocket.request_headers['agent']
            agent_id = websocket.request_headers['agent_id']
        except KeyError:
            print("WARNING: Websocket missing critical Register field in request header.")
            return
        
        if agent not in self.allowed_agents:
            print(f"WARNING: Websocket made request with invalid agent {agent}.")
            return
        
        self.agent_to_websocket[agent_id] =  websocket


    async def unregister_websocket(self, websocket):
        print("Unregistering an old websocket connection.")
        try:
            agent_id = websocket.request_headers['agent_id']
        except KeyError:
            print(f"Warning: Websocket missing agent_id in the request header")
            return
        finally:
            self.agent_to_websocket.pop(agent_id, None)
            await websocket.close()
    

    ### Actions -- Error
    async def bad_action(self, parcel: IParcel, websocket):
        print(f"Error: Got a bad action! '{parcel['action']}'' in parcel {parcel}")
    

    async def bad_route(self, parcel: IParcel, websocket):
        print(f"ERROR: Got a bad route! '{parcel['route']}' in parcel {parcel}")
    

    # Actions -- Parcels
    async def open_here(self, parcel: IParcel, websocket):
        await self.actions[parcel['action']](parcel, websocket)
    

    async def route_to_other(self, parcel: IParcel, websocket):
        destination_websocket = self.agent_to_websocket[parcel['destination_id']]
        await destination_websocket.send(json.dumps(parcel))
    

    def new_service_pool(self, owner_id):
        return ServicePool(owner_id)


    ### Actions -- Services
    async def create_service(self, parcel: IParcel, websocket):
        target = parcel['data']['target']
        task = self.tasks[target]

        args = parcel['data']['args']
        kwargs = {
            'connection_config': self.connection_config
        }
        kwargs.update(parcel['data']['kwargs'])

        owner_id = websocket.request_headers['agent_id']
        params = { 'args': args, 'kwargs': kwargs }

        service_pool = self.agent_to_services.get(owner_id, None)
        if not service_pool:
            service_pool = ServicePool(owner_id)
            self.agent_to_services[owner_id] = service_pool
        
        hash = parcel['data']['hash']
        service = Service(owner_id, websocket, task, params)
        service_pool.add_service(hash, service)
        service.run()


    async def close_service(self, parcel: IParcel, websocket):
        agent_id = websocket.request_headers['agent_id']
        hash = parcel['data']['hash']
        
        service_pool: ServicePool = self.agent_to_services[agent_id]
        service_pool.close_service(hash)


    def extend_tasks(self, key: str, task: Callable):
        self.tasks[key] = task


    ### Tasks
    async def do_work(self):
        print("Starting Servman.")

        extra_headers = [
            ('agent', 'servman'),
            ('agent_id', self.agent_id)
        ]

        async def handle_websocket(websocket, request_path):
            print("Handling websocket")
            await self.register_websocket(websocket)
            
            async for message in websocket:
                try:
                    parcel: IParcel = json.loads(message)
                    await self.routes[parcel['routing']](parcel, websocket)
                except JSONDecodeError:
                    print(f"Error in ServiceManager.handle_websocket: {e}")
                    print(f"Message not encoded in JSON.")
                except Exception as e:
                    print(f"Error in ServiceManager.handle_websocket: {e}")
                    traceback.print_exc()
                    new_parcel: IParcel = {
                        'routing': parcel['agent'],
                        'action': 'handle_error',
                        'data': f"Error in ServiceManager: {e}"
                    }
                    await websocket.send(json.dumps(new_parcel))

            await self.unregister_websocket(websocket)

        self.server = await websockets.serve(
            handle_websocket,
            host=self.host,
            port=self.port,
            max_queue=1024,
            max_size=None,
            extra_headers=extra_headers,
            origins=[None]
        )

        while True:
            await asyncio.Future()


    def run(self):
        multiprocessing.set_start_method("spawn")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())