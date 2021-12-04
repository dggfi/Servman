"""

Action implementation leans heavily on command cogs designs inside of discord.py

discord.py Copyright (c) 2015-2021 Rapptz MIT License
pycord Copyright (c) 2021-present Pycord Development MIT License

"""


import asyncio
from asyncio.queues import Queue
from collections import defaultdict
from typing import Any, Callable, Dict, Type, TypeVar
import json
import traceback
from uuid import uuid4 as uuidv4
import websockets
from servman. typings import IParcel
import inspect
from servman.ext import ActionCollision
from time import time

# Types
ActionT = TypeVar('ActionT', bound='Action')
AgentT = TypeVar('AgentT', bound='Agent')


class Action:

    __original_kwargs__: Dict[str, Any]

    def __new__(cls: Type[ActionT], *args: Any, **kwargs: Any) -> ActionT:
        self = super().__new__(cls)
        self.__original_kwargs__ = kwargs.copy()
        return self
    
    def __init__(self, func, *args, **kwargs) -> None:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        self.callback = func
        self.agent = None

        name = kwargs.get("name") or func.__name__
        self.name = name

        description = kwargs.get("description") or (
            inspect.cleandoc(func.__doc__).splitlines()[0]
            if func.__doc__ is not None
            else "No description provided."
        )
        self.description = description

        self.aliases = (kwargs.get("aliases") + [self.name]) if (kwargs.get("aliases")) else [self.name]

    async def __call__(self, parcel: IParcel):
        return await self.callback(self.agent, parcel)
    
    def copy(self: ActionT) -> ActionT:
        return self.__class__(self.callback, **self.__original_kwargs__)
    
    def _update_copy(self: ActionT, kwargs: Dict[str, Any]) -> ActionT:
        if kwargs:
            kw = kwargs.copy()
            kw.update(self.__original_kwargs__)
            return self.__class__(self.callback, **kw)
        else:
            return self.copy()

    # Not sure that this is needed
    def to_dict(self) -> Dict:
        as_dict = {
            "name": self.name,
            "description": self.description,
            "aliases": self.aliases
        }
        return as_dict


def action(cls=Action, **attrs):
    """
        The decorator you will use to register actions.

        Attributes
        -----------
        name: :class:`str`
            The name the Action will register under.
        description: :class:`str`
            If no descripton is provided, it will be pulled from the docstrings.
        aliases: :class:`list`
            A list of all the `str` keys your Action can be invoked under.
            Name collisions will throw an error.
        cls: :class:`Any`
            Any optional subclass of Action. Defaults to Action
    """
    def decorator(func: Callable) -> cls:
        if isinstance(func, Action):
            func = func.callback
        elif not callable(func):
            raise TypeError(
                "func needs to be a callable or a subclass of Action."
            )
        return cls(func, **attrs)

    return decorator



class Agent:
    def __init__(self):
        """
            An Agent is a Cog-like that has actions.
        """
        self._actions = defaultdict(self.return_bad_callback, {}) # only the callbacks

        self.inject_actions(self)

    # Actions / injectors
    def inject_action(self, action: Action, overwrite=False, graft=False):
        registered = self._actions.get(action.name, None)
        if registered and not overwrite:
            print("Error: Action naming collision!")
            print(f"Action {action.name} would overwrite another action {registered.name}")
            raise ActionCollision
        
        if not graft:
            action.agent = self

        aliases = set(action.aliases)
        for alias in aliases:
            action_registered = self._actions.get(alias, None)
            if overwrite or not action_registered:
                self._actions[alias] = action
            else:
                print("Error: Action naming collision!")
                print(f"Action {action.name} with alias {alias} would overwrite another action {registered.name}")
                del self._actions[action.name]
                raise ActionCollision

    def inject_actions(self, agent: AgentT=None, overwrite=False, graft=False):
        """
            Register all Actions that the agent is aware of.
            If an agent is not provided, it will default to the instance.

            When overwrie is set to True, it will not throw an error
            if there is a name collision.
        """
        agent = agent or self
        if not isinstance(agent, Agent):
            raise TypeError(f"Obj {agent} must be an instance of a ServmanAgent for injection")

        for name in dir(agent):
            attr = getattr(agent, name)
            if isinstance(attr, Action):
                self.inject_action(attr, overwrite, graft)
    
    def return_bad_callback(self): return self.bad_callback



class ServmanAgent(Agent):
    def __init__(self, connection_config, *args, **kwargs):
        """
            Use this class helper to create a Client or Service. 
            The notes here will guide you in creating a Client-ServiceManager-Service
            throughline to organize your project.

            Agent in config should be assigned either of 'client' or 'service'.
        """
        super().__init__(*args, **kwargs)

        # Connection
        self._connection_config = connection_config
        self._primary_websocket = None # Connection to servman
        self._primary_connection_ids = {} # identifer: connection_id
        self._proxy_websockets = {} # purpose: websocket
        self._proxy_connection_ids = {} # purpose: connection_id, for destinations
        self._proxy_connected = {} # purpose: boolean
        self._proxy_connecting = {} # purpose: routine

        # Specific to services
        self.identifier = kwargs.get('identifier', None)

        # Queues
        self._primary_message_queue = Queue()
        self._proxy_message_queues = {} # purpose: Queue

        # Identity
        self._agent = connection_config['agent']
        self._agent_id = str(uuidv4())
        self._primary_connection_id = str(uuidv4())

        # State
        self._primary_connected = False

        # Options
        self._connection_timeout = kwargs.get('connection_timeout', 1)
    

    # Actions
    """
        Actions are the principal way Clients and Services tell
        each other what to do. A Client may send a "ping" action
        to a Service and then the same Service could respond by 
        sending a "pong" action back to the Client.

        You will benefit from having a way to catch action look-up
        failure. We will be using a defaultdict for this.

        Note: The current implementation only allows for coroutines.   
    """

    # Registering Actions
    """
        You have two options for registering an Action. The recommended
        way is to use the @action decorator. This will generally prevent
        future breakage.

        If you want to add actions manually, you can do so with direct
        assignment:

        self._actions[k] = ActionT
    """

    # Example action
    """
        In many cases you will want to delay performing
        logic until a Service is initialized running. Once
        Service setup is completed, have it send a finalize
        action back to the Client. For example:

        @action()
        async def finalize(self, parcel: IParcel):
            pass
    """

    ### Actions / Services events
    @action()
    async def catch_service_credentials(self, parcel: IParcel, websocket, queue):
        """
            A service that has just been created should send these.
        """
        print("ayayaya")
        identifier = parcel['data']['identifier']
        connection_id = parcel['data']['connection_id']
        self._primary_connection_ids[identifier] = connection_id
        print(self.on_service_created)
        try:
            await self.on_service_created(identifier, connection_id, websocket, queue)
        except Exception as e:
            print(e)
        finally:
            print("Uh okay then")

    ### Actions / Proxies
    @action()
    async def catch_proxy_credentials(self, parcel: IParcel, websocket, queue):
        """
            Servman will send this action when a pipeline has been bridged.
        """
        purpose = parcel['data']['purpose']
        connection_id = parcel['data']['connection_id']
        self._proxy_connection_ids[purpose] = connection_id
        self._proxy_connected[purpose] = True
        await self.on_bridge(purpose, connection_id, websocket, queue)

    @action()
    async def bridge_pipeline(self, parcel: IParcel, websocket, queue):
        """
            This action is usually reserved for a Service to complete
            a bridge.
        """
        purpose = parcel['data']['purpose']
        identifier = parcel['data']['identifier']
        await self.new_proxy_connection(identifier, purpose)

    ### Actions / Error handling
    @action()
    async def handle_servman_error(self, parcel: IParcel, websocket, queue):
        """
            This action is dispatched from Servman whenever
            there is an error.
            
            The most common error will likely be key errors.
        """
        excp = parcel['data']['exception']
        message = parcel['data']['message']
        print(f"Received error from Servman: {excp} {message}")

    @action()
    async def handle_security_alert(self, parcel: IParcel, websocket, queue):
        """
            Servman will dispatch this whenever there is a potential
            threat, i.e. anyone besides the service owner attempting
            to close the service.
        """
        alert = parcel['data']['alert']
        message = parcel['data']['message']
        print(f"Received security alert from Servman: {alert} {message}")


    ### Actions / Close
    @action()
    async def close(self, parcel: IParcel, websocket, queue):
        """
            You will often want to override this action.
        """
        exit()

    @action()
    async def force_close(self, parcel: IParcel, websocket, queue):
        exit()


    ### Events
    # You can override these for custom behavior
    async def on_connect(self, websocket, queue):
        pass

    async def on_bridge(self, purpose, connection_id, websocket, queue):
        pass

    async def on_service_created(self, identifier, connection_id, websocket, queue):
        pass

    # Websocket
    async def connect(self):
        """
            The initial connection phase.
        """
        host = self._connection_config['host']
        port = self._connection_config['port']
        connection_uri = f"ws://{host}:{port}"

        extra_headers = [
            ('agent', self._connection_config['agent']),
            ('agent_id', self._agent_id),
            ('connection_id', self._primary_connection_id),
            ('proxy', 'false')
        ]

        connected = False
        timeout = self._connection_timeout
        T_EPOCH = time()
        while not connected and not (time() - T_EPOCH) > 10:
            try:
                self._primary_websocket = await websockets.connect(
                    connection_uri,
                    extra_headers=extra_headers
                )
                connected = True
            except ConnectionRefusedError:
                print(f"Connection refused for ServmanAgent with ID {self._agent_id}. Sleeping for one second...")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"ServmanAgent with ID {self._agent_id} failed to connect!")
                print(e)
                traceback.print_exc()
                exit()
        
        # Add service to pool
        if self._connection_config['agent'] == 'service':
            request: IParcel = {
                'routing': 'servman',
                'action': 'hook_into_pool',
                'data': { 'identifier': self.identifier }
            }
            await self._primary_message_queue.put(json.dumps(request))

        await self.on_connect(self._primary_websocket, self._primary_message_queue)
        self._primary_connected = True

    async def new_proxy_connection(self, identifier, purpose):
        """
            To create a new proxy connection, you will need
            the identifier for an existing service. The `purpose`
            argument will help identify the new client-to-service
            connection.

            This will automatically run consumers and producers for the new connection.
        """
        host = self._connection_config['host']
        port = self._connection_config['port']
        connection_uri = f"ws://{host}:{port}"

        connection_id = str(uuidv4())

        extra_headers = [
            ('agent', self._agent),
            ('agent_id', self._agent_id),
            ('connection_id', connection_id),
            ('proxy', 'true'),
            ('identifier', identifier),
            ('purpose', purpose)
        ]

        new_websocket = None
        try:
            new_websocket = await websockets.connect(
                connection_uri,
                extra_headers=extra_headers
            )
        except Exception as e:
            print(f"Service with ID {self._agent_id} failed to establish a new socket connection!")
            print(e)
            traceback.print_exc()
            return

        self._proxy_websockets[purpose] = new_websocket
        self._proxy_connected[purpose] = False
        self._proxy_connecting[purpose] = self.new_wait_until_connected(purpose)
        
        queue = Queue()
        self._proxy_message_queues[purpose] = queue
        self.run_consumer(new_websocket, queue)
        self.run_producer(new_websocket, queue)

               
    def new_wait_until_connected(self, purpose):    
        async def new_wait_until_connected():
            T_EPOCH = time()
            while not self._proxy_connected[purpose]:
                await asyncio.sleep(0)
        
        return new_wait_until_connected

    async def wait_until_connected(self):
        while not self._primary_connected:
            await asyncio.sleep(0)

    # Websocket / Messages
    """
        Messages are passed over the network in the form of Parcels.
        The structure of a Parcel is a dict that has these entries:

        interface Parcel {
            'routing': 'servman' or 'client' or 'service',
            'destination_id': str,
            'action': str,
            'data': Any
        }

        The routing property informs the ServiceManager what it should
        do with a message it receives. Generally you will only route messages
        to the ServiceManager when you want to Service controls (such as creating
        or deleting a Service).

        The destination_id should be the ID of the Service (or Client, or 
        any future implementation, really) that you wish to send a message to.

        The action is the coroutine you wish for the receiver to invoke.

        Data should include everything the action invokation needs.
        Since it is your service, it is entirely up to you how you
        implement this structure.

        Any outgoing messages should be placed in the message queue.
    """


    # Websocket / Consuming and Producing messages
    """
        You will need a pair of tasks to consume incoming websocket
        messages and a way to send out messages that have been queued.
    """
    def run_consumer(self, websocket, queue):
        loop = asyncio.get_event_loop()
        
        async def new_consumer():
            while True:
                packet = await websocket.recv()
                parcel: IParcel = json.loads(packet)
                # Warning careful not to block the consumer
                action = self._actions[parcel['action']]
                loop.create_task(action.callback(action.agent, parcel, websocket, queue))

        loop.create_task(new_consumer())
    
    def run_producer(self, websocket, queue):
        loop = asyncio.get_event_loop()

        async def new_producer():
            while True:
                await websocket.send(await queue.get())
        
        loop.create_task(new_producer())            

    async def consume(self):
        await self.wait_until_connected()

        loop = asyncio.get_event_loop()
        try:
            while True:
                packet = await self._primary_websocket.recv()
                parcel: IParcel = json.loads(packet)
                # Warning: careful to not block the consumer
                action = self._actions[parcel['action']]
                print(f"{self._agent} {self} Got an action: {parcel['action']}")
                print(action)
                print(action.agent)
                print()
                loop.create_task(action.callback(action.agent, parcel, self._primary_websocket, self._primary_message_queue))
        except Exception as e:
            print(e)


    async def produce(self):
        await self.wait_until_connected()

        while True:
            await self._primary_websocket.send(await self._primary_message_queue.get())


    def get_tasks(self):
        return [
            self.connect,
            self.consume,
            self.produce
        ]

    # Event loop
    async def do_work(self):
        tasks = [t() for t in self.get_tasks()]
        await asyncio.gather(*tasks)


    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())