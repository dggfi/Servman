import multiprocessing
import asyncio
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
import traceback, logging
import json
from json.decoder import JSONDecodeError
from path import Path
from uuid import uuid4 as uuidv4
from collections import defaultdict
from typings import IConnectionConfig, IParcel
from service_pool import ServicePool, Pipeline
from typing import Callable


class ServiceManager:
    """
        A task scheduler and communication proxy between clients
        and scheduled tasks called services. Server-like.

        The ServiceManager object is the core of the servman project.
        Basic usage is to create a ServiceManger and then tell it which tasks
        you would like to run. Meanwhile, it will automatically create a websocket
        server based on the configuration file you provide for it. You usually
        will want to design your Client and corresponding Service to connect
        to the ServiceManager.

        A simple heartbeat.py project is available in the examples folder.
        For a more complex integration, checkout the MafiaBot project which
        uses discord.py (https://github.com/dggfi/MafiaBot)
    """
    def __init__(self, config_path):
        self._agent_id = str(uuidv4())

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
            'create_service': self.create_service,
            'join_service_pool': self.join_service_pool,
            'hook_into_pool': self.hook_into_pool,
            'kill': self.kill,
        }

        def return_bad_action(): return self.bad_action
        self._actions = defaultdict(return_bad_action, actions)

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
        self.id_to_websocket = {} # connection_id: websocket
        self.identifier_to_service_pools = {} # identifier: ServicePool
        self.tasks = {} # str: Callable
        self.client_pool_identifiers = {} # agent_id: set([identifiers])
        self.pending_pipelines = {}

        # Misc.
        self.t_ping = None
        self.logger = logging.getLogger("websockets.server")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(logging.StreamHandler())
        self.n_messages = 0
    
        # Security
        self.secret = 'my_secret'


    ### Websocket
    async def register_websocket(self, websocket):
        agent = ''
        connection_id = ''
        proxy = 'false'
        try:
            agent = websocket.request_headers['agent']
            connection_id = websocket.request_headers['connection_id']
            proxy = websocket.request_headers['proxy']
        except KeyError:
            response: IParcel = { 
                'routing': websocket.request_headers['agent'],
                'action': 'handle_servman_error',
                'data': { 'exception': 'HeaderMissing', 'message': "Websocket missing critical field in request header." }
            }
            await websocket.send(json.dumps(response))
            await websocket.close()
            return
        
        if agent not in self.allowed_agents:
            response: IParcel = { 
                'routing': websocket.request_headers['agent'],
                'action': 'handle_servman_error',
                'data': { 'exception': 'HeaderMissing', 'message': "Websocket missing critical field in request header." }
            }
            await websocket.send(json.dumps(response))
            await websocket.close()
            return
        
        # Test whether the websocket is an original agent-to-servman connection
        # or if it should be a proxy connection        
        existing_socket = self.id_to_websocket.get(connection_id, None)
        if existing_socket:
            response: IParcel = {
                'routing': agent,
                'action': 'handle_servman_error',
                'data': { 'parcel': None, 'exception': 'ConnectionExists', 'message': f"Websocket with agent_id/connection_id {connection_id} already exists!" }
            }
            await existing_socket.send(json.dumps(response))
            await websocket.close()
            return

        self.id_to_websocket[connection_id] = websocket
        if proxy == 'true':
            await self.build_pipeline(websocket)


    async def unregister_websocket(self, websocket):
        """
            There may be concurrency issues when a client with multiple
            connections drops.
        """
        print(f"Unregistering {websocket.request_headers['agent_id']}")

        connection_id = websocket.request_headers['connection_id']

        # Remove references
        self.id_to_websocket.pop(connection_id)
        agent_id = websocket.request_headers['agent_id']
        if agent_id in self.client_pool_identifiers:
            identifiers = self.client_pool_identifiers[agent_id]
            identifiers = set([i for i in identifiers if i in self.identifier_to_service_pools])
            orphaned_identifiers = set([i for i in identifiers if websocket is self.identifier_to_service_pools[i].owner_websocket and self.identifier_to_service_pools[i].close_on_disconnect])
            identifiers = identifiers - orphaned_identifiers
            if identifiers:
                self.client_pool_identifiers[agent_id] = identifiers
            else:
                if agent_id in self.client_pool_identifiers: self.client_pool_identifiers.pop(agent_id)
            for identifier in orphaned_identifiers:
                pool = self.identifier_to_service_pools.pop(identifier)
                # Defer socket closure to service pool
                await pool.close(agent_id)
        

    ### Actions -- Error
    async def bad_action(self, parcel: IParcel, websocket):
        print(f"Error: Got a bad action! '{parcel['action']}'' in parcel {parcel}")
    

    async def bad_route(self, parcel: IParcel, websocket):
        print(f"Error: Got a bad route! '{parcel['route']}' in parcel {parcel}")
    

    # Actions -- Parcels
    async def open_here(self, parcel: IParcel, websocket):
        await self._actions[parcel['action']](parcel, websocket)


    async def route_to_other(self, parcel: IParcel, websocket):
        destination_websocket = self.id_to_websocket[parcel['destination_id']]
        await destination_websocket.send(json.dumps(parcel))


    ### Actions -- Services
    async def create_service(self, parcel: IParcel, websocket):
        identifier = parcel['data']['kwargs']['identifier']

        # Check for existing service pool
        existing_service_pool: ServicePool = self.identifier_to_service_pools.get(identifier, None)
        if existing_service_pool and websocket is existing_service_pool.owner_websocket:
            response: IParcel = {
                'routing': websocket.request_headers['agent'],
                'action': 'handle_servman_error',
                'data': { 'exception': 'ServiceCollision', 'message': f'Service with identifier {identifier} already exists' }
            }
            await websocket.send(json.dumps(response))
            return
        elif existing_service_pool and not websocket is existing_service_pool.owner_websocket:
            agent_id = websocket.request_headers['agent_id']
            response: IParcel = {
                'routing': websocket.request_headers['agent'],
                'action': 'handle_security_alert',
                'data': { 'alert': 'ServiceCollision', 'message': f"Agent with ID {agent_id} attempted to overwrite existing service {identifier}" }
            }
            await existing_service_pool.owner_websocket.send(json.dumps(response))
            return
        # No service_pool found? Let's make one
        target = parcel['data']['target']
        task = self.tasks[target]

        args = parcel['data']['args']
        kwargs = parcel['data']['kwargs']

        owner_id = websocket.request_headers['agent_id']
        params = { 'args': args, 'kwargs': kwargs }

        options = parcel['data']['options']

        new_service_pool = ServicePool(identifier, owner_id, websocket, task, params, **options)
        self.identifier_to_service_pools[identifier] = new_service_pool

        agent = websocket.request_headers['agent']
        if agent == 'client':
            agent_id = websocket.request_headers['agent_id']
            if agent_id in self.client_pool_identifiers:
                self.client_pool_identifiers[agent_id].add(identifier)
            else:
                self.client_pool_identifiers[agent_id] = set([identifier])

        new_service_pool.run()

    async def join_service_pool(self, parcel: IParcel, websocket):
        """
            A client may join a service pool through this action.
        """
        identifier = parcel['data']['identifier']
        service_pool = await self.get_service_pool(identifier, websocket)
        if service_pool:
            await service_pool.add_client_connection(websocket)

    async def hook_into_pool(self, parcel: IParcel, websocket):
        """
            Every service should send this action once.

            Hook logic is implemented by default in the ServmanAgent
            helper.
        """
        identifier = parcel['data']['identifier']
        service_pool: ServicePool or None = await self.get_service_pool(identifier, websocket)
        if service_pool: 
            service_pool.service_connection = websocket

    async def close_service(self, parcel: IParcel, websocket):
        identifier = parcel['data']['service_identifer']
        service_pool: ServicePool = await self.get_service_pool(identifier, websocket)
        if service_pool:
            await service_pool.close(identifier)
    
    async def kill(self, parcel: IParcel, websocket):
        secret = parcel['data']['secret']
        if secret == self.secret:
            print("Killing Servman. Good bye!")
            try:
                exit()
            except BaseException:
                exit()
        else:
            print(f"Connection with ID {websocket.request_headers['connection_id']} attempted to kill Servman but failed to guess its secret.")

    def register_task(self, key: str, task: Callable):
        if self.tasks.get(key, None):
            pass
        self.tasks[key] = task

    ### Prefabs / Get
    async def get_service_pool(self, identifier, websocket):
        service_pool: ServicePool = self.identifier_to_service_pools.get(identifier, None)
        if not service_pool:
            response: IParcel = { 
                'routing': websocket.request_headers['agent'],
                'action': 'handle_servman_error',
                'data': { 'exception': 'ServicePoolNotFound', 'message': f"Service pool with identifier {identifier} not found" }
            }
            await websocket.send(json.dumps(response))
            return None
        else:
            return service_pool
    
    ### Prefabs / Other
    async def build_pipeline(self, websocket):
        """
            Clients and services communicate through a Pipeline. A client
            may establish any number of Pipelines. This may change
            in the future.
        """
        # First identify the service
        identifier = ''
        purpose = ''
        try:
            identifier = websocket.request_headers['identifier']
            purpose = websocket.request_headers['purpose']
        except KeyError:
            print("KeyError in build_pipeline")
            return


        identifier = websocket.request_headers['identifier']
        service_pool = await self.get_service_pool(identifier, websocket)
        if not service_pool:
            return

        purpose = websocket.request_headers['purpose']
        pipeline: Pipeline = service_pool.pipelines.get(purpose, None)
        if not pipeline:
            pipeline = Pipeline(purpose)
            service_pool.pipelines[purpose] = pipeline

        agent = websocket.request_headers['agent']
        if agent == 'client':
            pipeline.client_connection_id = websocket.request_headers['connection_id']
            pipeline.client_connection = websocket
        elif agent == 'service':
            pipeline.service_connection_id = websocket.request_headers['connection_id']
            pipeline.service_connection = websocket
        
        if not pipeline.bridged and pipeline.client_connection and pipeline.service_connection:
            pipeline.connections[pipeline.client_connection] = pipeline.service_connection
            pipeline.connections[pipeline.service_connection] = pipeline.client_connection

            client_parcel = {
                'routing': 'client',
                'action': 'catch_proxy_credentials',
                'data': {'purpose': purpose, 'connection_id': pipeline.service_connection_id }
            }
            service_parcel = {
                'routing': 'service',
                'action': 'catch_proxy_credentials',
                'data': {'purpose': purpose, 'connection_id': pipeline.client_connection_id }
            }
            await pipeline.client_connection.send(json.dumps(client_parcel))
            await pipeline.service_connection.send(json.dumps(service_parcel))
            pipeline.bridged = True
        elif not pipeline.bridged and pipeline.client_connection and not pipeline.service_connection:
            bridge_service_parcel = {
                'routing': 'service',
                'action': 'bridge_pipeline',
                'data': { 'purpose': purpose, 'identifier': identifier }
            }
            await service_pool.service_connection.send(json.dumps(bridge_service_parcel))
        else:
            print("@@@@@@@@@@@@@@@@@@@@@@@@ >< This should never happen. Synchronization error? Bad request?")

    ### Tasks
    async def run_server(self):
        print("Starting Servman.")

        extra_headers = [
            ('agent', 'servman'),
            ('agent_id', self._agent_id)
        ]

        async def handle_websocket(websocket, request_path):
            await self.register_websocket(websocket)
            
            try:
                async for message in websocket:
                    self.n_messages += 1
                    parcel: IParcel = json.loads(message)
                    await self.routes[parcel['routing']](parcel, websocket)
            except JSONDecodeError:
                print(f"JSON Error in ServiceManager.handle_websocket: Message not encoded in JSON.\n\n")
            except ConnectionClosedError:
                print(f"Websocket {websocket} closed unexpectedly.")
            except Exception as e:
                print(f"\n\nOther Error in ServiceManager.handle_websocket: {e}\n\n")
                traceback.print_exc()
                new_parcel: IParcel = {
                    'routing': parcel['routing'],
                    'action': 'handle_servman_error',
                    'data': { 'parcel': parcel, 'exception': e.__str__(), 'message': 'exception occurred while handling websocket' }
                }
                await websocket.send(json.dumps(new_parcel))

            await self.unregister_websocket(websocket)

        self.server = await websockets.serve(
            handle_websocket,
            host=self.host,
            port=self.port,
            max_queue=2048,
            max_size=None,
            extra_headers=extra_headers,
            origins=[None]
        )

        while True:
            await asyncio.Future()


    async def print_metrics(self):
        while True:
            await asyncio.sleep(3)
            print(f"Received {self.n_messages} messages, servicing {len(self.id_to_websocket.values())} websockets and {len(self.identifier_to_service_pools.keys())} active agents.")


    async def do_work(self):
        tasks = [
            self.run_server(),
            self.print_metrics()
        ]
        await asyncio.gather(*tasks)

    def run(self):
        multiprocessing.set_start_method("spawn")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())