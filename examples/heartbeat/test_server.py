from servman import ServiceManager
from heartbeat import pong_service

if __name__ == "__main__":
    config_path = "conf/server_configuration.json"

    sm = ServiceManager(config_path)
    sm.extend_tasks('heartbeat', pong_service)
    sm.run()