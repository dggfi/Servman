from typing import Any, TypedDict, Literal

"""
    INTERFACES

    websocket headers interface
    {
        'agent_type': 'discord_client' | 'web_client' | 'service',
        'connection_id': string
    }
"""

class IParcel(TypedDict):
    routing: Literal['servman'] or Literal['client'] or Literal['service']
    origin_id: str
    destination_id: str
    action: str
    data: Any

class IConnectionConfig(TypedDict):
    host: str
    port: int

class IServmanConfig(IConnectionConfig):
    logging: bool
