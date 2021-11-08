from multiprocessing import Process

class Service:
    def __init__(self, owner_id, owner_websocket, target, params):
        self.owner_id = owner_id
        self.owner_websocket = owner_websocket
        self.process = Process(
            target=target,
            args=params['args'],
            kwargs=params['kwargs']
        )
        self.initiated = False
    
    def run(self):
        self.initiated = True
        print("Running a new service.")
        self.process.start()
    
    def close(self):
        self.process.close()


class ServicePool:
    def __init__(self, owner_id):
        self.owner_id = owner_id
        self.services = {} # hash: service
        self.hashes = {} # hash: encryption
    
    def add_service(self, hash, service):
        self.services[hash] = service
    
    def close_service(self, hash):
        service = self.services.pop(hash)
        service.close()