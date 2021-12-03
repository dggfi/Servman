re='^[0-9]+$'
if ! [[ $1 =~ $re ]] ; then
   echo "Heartbeat test requires a number argument (number of clients to be created)" >&2; exit 1
fi

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

# Configuration
mkdir conf
echo "{\"host\": \"127.0.0.1\", \"port\": 8000, \"agent\": \"client\"}" > conf/client_configuration.json
echo "{\"host\": \"127.0.0.1\", \"port\": 8000, \"agent\": \"servman\"}" > conf/server_configuration.json
echo "{\"host\": \"127.0.0.1\", \"port\": 8000, \"agent\": \"service\"}" > conf/service_configuration.json

cp examples/heartbeat/* src/servman/

# Server
python3 src/servman/heartbeat_server.py &

# Clients
python3 src/servman/heartbeat_clients.py $1

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