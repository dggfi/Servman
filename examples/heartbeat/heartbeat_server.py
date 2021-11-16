from servman import ServiceManager
from service import pong_service

if __name__ == "__main__":
    config_path = "conf/server_configuration.json"

    sm = ServiceManager(config_path)
    sm.register_task('heartbeat', pong_service)
    sm.run()