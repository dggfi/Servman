from typing import Literal, Any

class Parcel:
    def __init__(
        self,
        routing: Literal['servman'] or Literal['client'] or Literal['service'],
        destination_id: str,
        action: str,
        data: Any
    ):
        self.routing = routing
        self.destination_id = destination_id
        self.action = action
        self.data = data