from typing import Any, TypedDict, Literal

"""
    MISC

    websocket headers
    {
        'agent': 'servman' | 'client' | 'service',
        'agent_id': string,
        'connection_id'?: string
    }
"""

class IParcel(TypedDict):
    routing: Literal['servman'] or Literal['client'] or Literal['service']
    destination_id: str
    action: str
    data: Any

class IConnectionConfig(TypedDict):
    host: str
    port: int

class IServmanConfig(IConnectionConfig):
    logging: bool