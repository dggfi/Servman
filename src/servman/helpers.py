from abc import ABC, abstractmethod
import asyncio
from asyncio.queues import Queue
from collections import defaultdict
from typing import Coroutine
import json
import traceback
from uuid import uuid4 as uuidv4

import websockets
from typings import IParcel

class ServmanAgent:
    """
        Use this class helper to create a Client or Service subclass. 
        The notes here will guide you in creating a Client-ServiceManager-Service
        throughline to organize your project.
    """
    def __init__(self, connection_config):
        """
            Agent type should be either of 'client' or 'service'
        """
        self._actions = defaultdict(self.return_bad_action, {})
        self._connection_config = connection_config

        # Public
        self.message_queue = Queue()

        # Identity
        self._agent_id = str(uuidv4())

        # State
        self._connected = False
        self._websocket = None
    
        # Collections
        self._actions = defaultdict(self.return_bad_action, self._actions)

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

    async def bad_action(self, parcel: IParcel):
        print(f"Client {self} received an invalid action: {parcel['action']}")

    def return_bad_action(self): return self.bad_action

    # Registering Actions
    """
        You have two options for registering an Action. One, you can simply
        add to the registry by direct assignment (self.actions[k] = f) or
        you can use the @action decorator. It has no side effects other than
        registering the function in place. This is generally much cleaner
        than maintaining a long list of actions in your subclass.
    """

    def action(self, f: Coroutine):
        self._actions[f.__name__] = f
        return f

    # Example action
    """
        In many cases you will want to delay performing
        logic until a Service is initialized running. Once
        Service setup is completed, have it send a finalize
        action back to the Client.
    """
    # @action
    # async def finalize(self, parcel: IParcel):
    #     pass


    # Websocket
    async def connect(self):
        host = self._connection_config['host']
        port = self._connection_config['port']
        connection_uri = f"ws://{host}:{port}"

        extra_headers = [
            ('agent', self._connection_config['agent']),
            ('agent_id', self._agent_id)
        ]

        try:
            self._websocket = await websockets.connect(
                connection_uri,
                extra_headers=extra_headers
            )
        except Exception as e:
            print(f"Service with ID {self._agent_id} failed to connect!")
            print(e)
            traceback.print_exc()
            exit()
        
        print(f"Success! Service with ID {self._agent_id} connected!")
        self._connected = True


    async def wait_until_connected(self):
        while not self._connected:
            await asyncio.sleep(0.1)


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
    async def consume(self):
        await self.wait_until_connected()

        loop = asyncio.get_event_loop()
        while True:
            packet = await self.websocket.recv()
            parcel: IParcel = json.loads(packet)
            # Warning: careful to not block the consumer
            action = self.actions[parcel['action']]
            loop.create_task(action(parcel))


    async def produce(self):
        await self.wait_until_connected()

        while True:
            await self.websocket.send(await self.message_queue.get())


    # Event loop
    async def do_work(self):
        tasks = [
            self.connect(),
            self.consume(),
            self.produce()
        ]
        await asyncio.gather(tasks)


    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_work())