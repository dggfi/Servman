import asyncio
from client import PingClient
import time
import json
from path import Path
from sys import argv

"""
    This test will create five hundred ping-pong client-service pairs.
    The client will ping, and the service will pong.
"""


if __name__ == "__main__":
    conf_file = Path("conf/client_configuration.json")
    if not conf_file.exists():
        print("Error: File config file doesn't exist")
        exit()
    connection_config = json.loads(conf_file.read_text(encoding='utf-8'))
    ping_clients = [PingClient(connection_config=connection_config) for x in range(int(argv[1]))]
    T_EPOCH = round(time.time() * 1000)
    async def do_work():
        all_tasks = [t() for c in ping_clients for t in c.get_tasks()]
        await asyncio.gather(*all_tasks)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_work())
    print(f"Test took {round(time.time() * 1000) - T_EPOCH}ms")