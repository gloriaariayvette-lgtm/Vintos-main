"""A test server inherits a reserved listener; it cannot accidentally reach a live port."""
import os

def install():
    if "VINTOS_TEST_LISTENER_FD" not in os.environ: return
    import socket, socketserver
    fd=int(os.environ["VINTOS_TEST_LISTENER_FD"])
    port=int(os.environ["VINTOS_TEST_PORT"])
    original=socketserver.TCPServer.server_bind
    def bind(server):
        if server.server_address[0] not in ("127.0.0.1","localhost") or server.server_address[1] not in (0,port):
            return original(server)
        server.socket.close()
        server.socket=socket.socket(fileno=os.dup(fd))
        server.server_address=server.socket.getsockname()
    socketserver.TCPServer.server_bind=bind
