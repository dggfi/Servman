import asyncio
from client import PingClient

"""
    This test will creat fifty ping-pong client-service pairs.
    The client will ping, and the service will pong.
"""


if __name__ == "__main__":
    ping_clients = [PingClient() for x in range(50)]
    print("Heartbeat client created.")
    async def do_work():
        all_tasks = [t() for c in ping_clients for t in c.get_tasks()]
        await asyncio.gather(*all_tasks)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_work())