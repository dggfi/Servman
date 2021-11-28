# Servman - the service manager

Servman schedules tasks inside of individual processes and exposes a websocket interface to communicate with them. This package works best as a reverse-proxy to tasks that are continuously running and benefit from a line of communication, i.e. multiplayer game instances.

## Usage guide

### Server

Import servman, instance a ServiceManager, and register the task you want to run from your own service module in a `server.py`:

```python
from servman import ServiceManager
from yourservice import myservice

if __name__ == "__main__":
    config_path = "conf/server_configuration"

    sm = ServiceManager(config_path)
    sm.register_task('myservice', myservice)
    sm.run()
```

Then run

> python3* server.py

### Client

If you are using the helpers class to create a client, you generally will follow this template code template inside of a `client.py`:

```python
from myclient import MyClientSubclass

if __name__ == "__main__":
    client = MyClientSubclass()
    client.run()
```

Then run

> python3* client.py

## Known issues

Debugging a process with hundreds to thousands of open websocket connections is hard. Here are the most likely ones that you will run into.

### Long time to establish connection

When connecting to localhost, you must wait for your machine to resolve the address. This sounds , but in personal tests it can delay the WebSocket handshake long enough to cause a timeout.

### File descriptor limit

Each open websocket connection requires a file to read and write from, if only in-memory. Many systems set a hard limit to number of these files available. If you open a ton of websocket connections (>500) only to see them begin dropping en masse, this is probably why.

Changing the file descriptor limit differs system to system. Ubuntu users can refer to this [this solution](https://askubuntu.com/questions/1049058/how-to-increase-max-open-files-limit-on-ubuntu-18-04). (Extra reading: the [How-To on ulimit and sysctl](https://www.linuxhowtos.org/Tips%20and%20Tricks/ulimit.htm))

### Connection throughput throttled or lost / memory or CPU limits reached

If the service instances are particularly numerous, sizable, or complex, you may want to consider sharding, using servman as a node, or other kinds of systems architecture techniques. Implementations of these systems designs may be developed for servman in the future.

## Tests

There is one automated test available, a heartbeat client-service pair. To run it,

> bash run_heartbeat_test.sh [n]

where `n` is the number of pairs you wish to create. Approximately four websocket connections will be created for each pair. The test will conclude in a spew about broken websocket connections. Additionally, using 500 or more of these pairs will likely cause breakage in many different ways even if your file descriptor limit is properly configured. To run it,

The Servman server *may* continue to run on its own when completed. You will have to manually kill the process and remove the copied files after. This test will be fixed in the future. You may run

> pkill -f python*

to kill all python processes on your machine for a full process clean-up. This may close your terminal.

## Future

Planned features include
* Admin tokens
* Supervisor mode
* Servman nodes
* Websocket SSL