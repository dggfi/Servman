from multiprocessing import Process
from servman.typings import IParcel
import json


class Pipeline:
    def __init__(self, purpose):
        """
            This represents a client-to-service proxy.
            You should provide a name that is fairly unique,
            such as f'{agent_id}_{connection_purpose}'
        """
        self.purpose = purpose

        self.client_connection = None
        self.service_connection = None

        self.client_connection_id = None
        self.service_connection_id = None

        self.connections = {} # websocket-to-websocket
        self.bridged = False


class ServicePool:
    def __init__(self, identifier, owner_id, owner_websocket, target, params, close_on_disconnect=True, filter_mode=None, connection_whitelist=None, connection_blacklist=None):
        self.identifier = identifier
        self.owner_id = owner_id
        self.owner_websocket = owner_websocket
        self.service_connection = None
        
        # Collections        
        self.clients_connections = {
            owner_id: owner_websocket
        }
        # websocket-to-websocket connections
        self.pipelines = {} # purpose: Pipeline

        # Service process
        self.process = Process(
            target=target,
            args=params['args'],
            kwargs=params['kwargs']
        )
        self.initiated = False

        # Options
        self.close_on_disconnect = close_on_disconnect
        self.filter_mode = filter_mode # 'whitelist' or 'blacklist' or None
        self.connection_whitelist = connection_whitelist or set([])
        self.connection_blacklist = connection_blacklist or set([])

    async def add_client_connection(self, websocket):
        agent_id = websocket.request_headers['agent_id']
        if (
            (self.filter_mode == 'whitelist' and not agent_id in self.connection_whitelist) or
            (self.filter_mode == 'blacklist' and agent_id in self.connection_blacklist)
        ):
            response = IParcel = {
                'routing': 'client',
                'action': 'handle_security_alert',
                'data': { 'alert': 'unauthorized_access', 'message': f'Requester with id {agent_id} attempted to join service {self.identifier}' }
            }
            await self.owner_websocket.send(json.dumps(response))
            return
        
        self.clients_connections[websocket.request_header['agent_id']] = websocket

    def run(self):
        self.initiated = True
        self.process.start()

    async def close(self, request_id):
        if request_id != self.owner_id:
            response: IParcel = {
                'routing': 'client',
                'action': 'handle_security_alert',
                'data': { 'alert': 'unauthorized_closure', 'message': f'Requester with id {request_id} attempted to close service {self.identifier}' }
            }
            await self.owner_websocket.send(json.dumps(response))
            return
        for socket in self.clients_connections.values():
            await socket.close()
        if self.service_connection:
            await self.service_connection.close()
        self.process.terminate()