# A simple load balancer developed in Python.
# - Supports multiple source IP addresses
# - Single threaded
# - Uses select so it only uses the necessary amount of CPU.
# Forward Motion Load Balancer

import socket
import select
import logging
import time
import sys
from datetime import datetime

LOG_FILENAME = 'logs/' + datetime.now().strftime('%d-%m-%Y_proxy.log')
HOST = ('', 34515)

logging.basicConfig(
    filename=LOG_FILENAME,
    format='%(asctime)s:%(levelname)s: %(message)s',
    level=logging.DEBUG
)


class BalanceServer(object):
    
    def __init__(self, host, nodes={}, source_ips={}):
        # People who have connected.
        self.connections = {}
        
        # The nodes the people will be connected to.
        self.nodes = nodes
        self.source_ips = source_ips
        
        # Create server listener
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(host)
        self.server.listen(5)
        
        # Message sizes.
        self.data_size = 1024
        
        self.node_selector = 0
        self.source_selector = 0
        self.running = False
        
        self.inputs = []
        self.client_ids = {}
        self.server_ids = {}
    
    # Callbacks
    def new_connection(self, client_id, node_id):
        "Callback for a new connection."
        pass
    
    def lost_connection(self, client_id):
        "Callback for a closed connection."
        pass
    
    def loop_cycle(self):
        "Callback when a loop cycle finishes."
        pass
    
    # Tools
    def get_next_node(self, client_id):
        self.node_selector = (self.node_selector + 1) % len(self.nodes)
        node = str(self.node_selector)
        source = self.get_source_ip(client_id)
        
        try:
            server_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_connection.bind((source, 0)) 
        except Exception, e:
            logging.critical(str(e) + ' ' + sys.exc_info()[0])
            try:
                server_connection.bind((source, 0))
            except:
                logging.critical(str(e))
        
        # Attempt to connect to the node.
        try:
            server_connection.connect(self.nodes[node])
        except socket.error, e:
            # Something is very wrong if we have a down node.
            if e[0] == 61:
                message = 'Could not connect to node: {1}. Error: {2}'
                message = message.format(node, e)
                logging.critical(message)
        
        return server_connection
    
    def get_source_ip(self, client_id):
        self.source_selector = (self.source_selector + 1) % len(self.source_ips)
        return str(self.source_selector)
    
    # Actions
    def close_connection(self, client_id):
        client = self.connections[client_id]
        message = str(client[0].getsockname()) + ' has disconnected from '
        message += str(client[1].getsockname()) + '.'
        logging.info(message)
        
        client[0].close()
        client[1].close()
        del self.client_ids[client[0]]
        del self.server_ids[client[1]]
        del self.connections[client_id]
        return (client[0], client[1])
    
    def proxy_client(self, client_id):
        "Proxy data for the connection"
        client = self.connections[client_id]
        client_socket = client[0]
        server_socket = client[1]
        data_size = self.data_size
        
        # Receive data from the client and send it to the server.
        try:
            client_recv = client_socket.recv(data_size)
            server_socket.send(client_recv)
            if not client_recv:
                return self.close_connection(client_id)
        
        except socket.error, e:
            # An error occurred on the client end, close connection.
            message = 'Client died! Error: ' + str(e)
            logging.warning(message)
            return self.close_connection(client_id)
        
        return []
    
    def proxy_server(self, client_id):
        "Proxy data for the connection"
        client = self.connections[client_id]
        client_socket = client[0]
        server_socket = client[1]
        data_size = self.data_size
        
        # Receive data from the server and send it to the client.
        try:
            server_recv = server_socket.recv(data_size)
            client_socket.send(server_recv)
            if not server_recv:
                return self.close_connection(client_id)
        
        except socket.error, e:
            # An error occurred on the server end, close connection.
            message = 'Server died! Error: ' + str(e)
            logging.warning(message)
            return self.close_connection(client_id)
        
        return []
    
    # Loop
    def run(self):
        server = self.server
        clients = self.connections
        nodes = self.nodes
        inputs = self.inputs
        
        client_ids = self.client_ids
        server_ids = self.server_ids
        
        running = self.running = True
        while running:
            inputs = client_ids.keys() + server_ids.keys() + [server]
            idata, odata, edata = select.select(inputs, [], [])
            
            for data in idata:
                if data == server:
                    # Accept new connection
                    connection, client_id = server.accept()
                    
                    # Get node connection
                    server_connection = self.get_next_node(client_id)
                    
                    # Save it to client list.
                    clients[client_id] = (connection, server_connection)
                    client_ids[connection] = client_id
                    server_ids[server_connection] = client_id
                    self.new_connection(client_id, server_connection)
                    
                    message = '{0} has connected to {1}.'.format(
                        client_id, server_connection.getsockname()
                    )
                    logging.info(message)
                
                elif data in client_ids:
                    client_id = client_ids[data]
                    self.proxy_client(client_id)
                    
                elif data in server_ids:
                    client_id = server_ids[data]
                    self.proxy_server(client_id)
            
            self.loop_cycle()


if __name__ == '__main__':
    server = BalanceServer(
        HOST,
        nodes={
            '0': ('127.0.0.1', 13003),
            '1': ('127.0.0.1', 13004),
        },
        source_ips={
            '0': socket.getfqdn(),
        }
    )
    server.run()
