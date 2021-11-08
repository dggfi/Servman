from heartbeat import PingClient

if __name__ == "__main__":
    # ping_clients = [PingClient() for x in range(10)]
    client = PingClient()
    print("Client created.")
    client.run()