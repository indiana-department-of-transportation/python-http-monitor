import re
from typing import Union
from ipaddress import IPv4Address
from threading import Thread
from functools import partial
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HOST = Union[str, IPv4Address]

# We only implement POST because of possibly sensitive requests,
# but again this server is intended for adding HTTP monitoring
# to multi-threaded python applications, not as a production HTTP
# web app server.
HTTP_METHODS = (
    'GET',
    'POST',
)

COMMA = r",\s*"
FOUR_OH_FOUR = """
<h1>HTTP 404</h1>
<p>The requested resource was not found</p>
"""


def format_route_key(route: str, method: str) -> str:
    return "{}, {}".format(route, method.upper())


class UnimplementedHTTPMethodError(Exception):
    pass


class TMCRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        print("CONSTRUCTOR CALL")
        super(TMCRequestHandler, self).__init__(request, client_address, server)
        print("POST INIT CALL")

    def do_GET(self):
        key = format_route_key(self.path, self.command)
        if key in self.server.route_rules:
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            result = self.server.route_rules[key]()
            self.wfile.write(str(result).encode())

        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(FOUR_OH_FOUR.encode())

    def do_POST(self):
        pass


class TMCHTTPServer(ThreadingHTTPServer):
    def __init__(
            self,
            rules={},
            address=("0.0.0.0", 8080),
            handler=TMCRequestHandler
        ):
        super(TMCHTTPServer, self).__init__(address, handler)
        self.route_rules = rules


class TMCServer(Thread):
    def __init__(
            self,
            host: HOST = "0.0.0.0",
            port: int = 8080,
            handler=TMCRequestHandler,
        ):
        super(TMCServer, self).__init__()
        self.__serving = False
        self.__addr = (str(host), port)
        self.__handler = handler
        self.__route_rules = {}
        self.daemon = True

    def add_url_handle(
            self,
            route,
            handler,
            methods = ["GET"],
        ):

        if self.__serving:
            # Technically we could allow this, but it isn't worth the
            # effort of tracking down subtle bugs from dynamically added
            # routes.
            raise AssertionError(
                "Invariant violation: cannot add route while server is running."
            )

        mthds = methods
        if isinstance(methods, str):
            mthds = list(re.split(COMMA, methods))
        
        for method in mthds:
            if not method.upper() in HTTP_METHODS:
                raise UnimplementedHTTPMethodError(
                    "TMCServer does not implement HTTP method {}".format(
                        method
                    )
                )

            key = format_route_key(route, method)
            if key in self.__route_rules:
                raise AssertionError(
                    """
                    Invariant violation: handler already registered for
                    route {} using method {}.
                    """.format(route, method.upper())
                )

            self.__route_rules[key] = handler

    def route(self, route, **opts):
        def decorator(func):
            self.add_url_handle(route, func, **opts)
            return func

        return decorator

    def run(self):
        self.__serving = True
        with TMCHTTPServer(
                self.__route_rules,
                self.__addr,
                self.__handler
            ) as server:
            while self.__serving:
                server.handle_request()

            print("\nServer exited.\n")

    def stop(self):
        self.__serving = False
