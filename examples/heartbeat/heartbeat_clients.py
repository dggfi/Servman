import asyncio
from client import PingClient
import time

"""
    This test will create five hundred ping-pong client-service pairs.
    The client will ping, and the service will pong.
"""


if __name__ == "__main__":
    ping_clients = [PingClient() for x in range(500)]
    print("Heartbeat client created.")
    T_EPOCH = round(time.time() * 1000)
    async def do_work():
        all_tasks = [t() for c in ping_clients for t in c.get_tasks()]
        await asyncio.gather(*all_tasks)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_work())
    print(f"Test took {round(time.time() * 1000) - T_EPOCH}ms")