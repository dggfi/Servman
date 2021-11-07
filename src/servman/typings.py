from typing import Any, TypedDict, Literal

"""
    INTERFACES

    websocket headers interface
    {
        'agent_type': 'discord_client' | 'web_client' | 'service',
        'connection_id': string
    }
"""

class Parcel(TypedDict):
    routing: Literal['servman'] or Literal['client'] or Literal['service']
    origin_id: str
    destination_id: str
    action: str
    data: Any

class Config(TypedDict):
    host: str
    port: int
    logging: bool