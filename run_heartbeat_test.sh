echo "Running a ping test."

# Purge
rm -rf venv/
rm -rf conf/

# Renew
python3 -m venv venv

# Work from local environment
source venv/bin/activate

# Install dependencies
python3 -m pip install -U websockets
python3 -m pip install -U path
python3 -m pip install -U bidict

# Configuration
mkdir conf
echo "{\"host\": \"localhost\", \"port\": 8000}" > conf/server_configuration.json

cp examples/heartbeat/* src/servman/

# Server
python3 src/servman/heartbeat_server.py &

# Clients
python3 src/servman/heartbeat_clients.py

# Done
deactivate

# Purge
rm -rf venv/
rm -rf conf/
rm src/servman/client.py
rm src/servman/service.py
rm src/servman/heartbeat_server.py
rm src/servman/heartbeat_clients.py

echo "Tests complete."