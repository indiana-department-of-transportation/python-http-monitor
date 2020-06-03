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


def _default_error_handler(err: Exception):
    print(err)
    return err


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
            on_error=_default_error_handler,
        ):
        super(TMCServer, self).__init__()
        self.daemon = True  

        # NOTE: Setting these public attributes has no effect once
        # start is called.
        self.port = port
        self.host = host
        self.address = (str(host), port)

        self.__serving = False
        self.__handler = handler
        self.__route_rules = {}
        self.__on_error = on_error

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
        if not self.__route_rules:
            raise AssertionError(
                """
                Invariant Violation: Server has no route handlers and
                will return a 404 for every request.
                """
            )
        self.__serving = True
        with TMCHTTPServer(
                self.__route_rules,
                self.address,
                self.__handler
            ) as server:
            while self.__serving:
                try:
                    server.handle_request()
                except Exception as err:
                    self.__on_error(err)

            print("\nServer exited.\n")

    def stop(self):
        self.__serving = False
