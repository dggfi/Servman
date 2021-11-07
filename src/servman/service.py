from multiprocessing import Process

class Service:
    def __init__(self, target, params):
        self.process = Process(
            target=target,
            args=params['args'],
            kwargs=params['kwargs']
        )
        self.initiated = False
    
    def run(self):
        self.initiated = True
        self.process.start()
    
    def close(self):
        self.process.close()

class TestTarget:
    def __init__(self, params):
        pass