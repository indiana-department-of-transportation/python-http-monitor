"""
.. py:module:: tmc_http_server
    :platform: *nix
    :synopsis: Defines a HTTP server designed for monitoring
        multithreaded Python3 applications. Not meant to e.g.
        define a RESTful API backend. The API is inspired by
        the Flask API.
"""
import re
from typing import Union, List, Dict, Tuple, Optional
from ipaddress import IPv4Address
from threading import Thread
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# For those who don't like their data stringly-typed.
HOST = Union[str, IPv4Address]
VERBS = Union[str, List[str]]
ADDRESS = Tuple[HOST, int]

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


def _default_error_handler(err: Exception) -> Exception:
    """Since the server runs in its own thread context, it
        can't simply raise an error for the caller to catch.
        The caller can provide an error handler as a
        callback when exceptions are raised, this is the
        default handler that simply prints to the console.

        :param err: The exception raised.
        :returns: The exception after printing.
    """
    print(err)
    return err


def format_route_key(route: str, method: str) -> str:
    """Formats an HTTP verb and the associated route into
        a dictionary key.

        :param route: The URL route.
        :param method: The HTTP method associated with the route.
        :returns: The formatted string.
    """
    return "{}, {}".format(route, method.upper())


class UnimplementedHTTPMethodError(Exception):
    """Exception raised when the user attempts to supply an
        unsupported HTTP verb. Since the route calls are
        direct, an exception can be raised to the caller
        rather than needing the callback mechanism used
        by request errors.
    """


class TMCRequestHandler(BaseHTTPRequestHandler):
    """Default request handler."""

    def do_GET(self):
        """Handles HTTP GET requests by calling the function
            associated with that route.
        """

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
        """TODO"""


class TMCHTTPServer(ThreadingHTTPServer):
    """This is the actual HTTP server that is in turn wrapped by TMCServer.

        :param rules: The mapping of routes to response functions.
        :param address: Tuple of (host, port).
        :param handler: Request handler should be TMCRequestHandler or a
            subclass of it.
    """
    def __init__(
            self,
            rules: Optional[Dict] = None,
            address: ADDRESS = ("0.0.0.0", 8080),
            handler=TMCRequestHandler
        ):
        """Initializer for TMCHTTPServer"""

        super(TMCHTTPServer, self).__init__(address, handler)
        self.route_rules = rules or {}


class TMCServer(Thread):
    """Wrapper class for TMCHTTPServer so that it can be run in
        a separate thread. Handles setup and tear down as well.

        :param host: The fully-qualified domain name or IP
            address of the server, defualts to '0.0.0.0'.
        :param port: The port number, defaults to 8080.
        :param handler: The request handler, defaults to
            TMCRequestHandler.
        :param on_error: Because the actual HTTP server runs in
            a separate thread, the caller can pass a callback
            here to receive errors that arise during requests.
    """
    def __init__(
            self,
            host: HOST = "0.0.0.0",
            port: int = 8080,
            handler=TMCRequestHandler,
            on_error=_default_error_handler,
        ):
        """Initializer for TMCHTTPServer"""

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
            methods: VERBS = "GET",
        ):
        """Registers the handler for the given route and HTTP
            verb. Although it can be called directly, it is likely
            more convenient to use the route decorator.

            :param route: The URL to register.
            :param handler: The handler function for that route.
            :param methods: The HTTP verbs that the route is valid for.
            :returns: self.
        """

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
            if method.upper() not in HTTP_METHODS:
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

        return self

    def route(self, route, **opts):
        """Decorator for adding a route with associated HTTP verbs
            and registering a handler function.

            :param route: The URL route to register.
            :param opts: The gathered keyword arguments.
            :returns: The decorator.
        """

        def decorator(func):
            """The inner decorator function.

                :param func: The handler to register.
                :returns: The handler.
            """
            self.add_url_handle(route, func, **opts)
            return func

        return decorator

    def run(self):
        """Override of the superclass Thread::run. Starts the HTTP Server
            and handles requests in an infinite loop that can be broken
            by calling TMCServer::stop.
        """
        if not self.__route_rules:
            self.__on_error(AssertionError(
                """
                Invariant Violation: Server has no route handlers and
                will return a 404 for every request.
                """
            ))
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
        """Stops the HTTP server. Don't forget to call TMCServer::join
            afterwards.
        """
        self.__serving = False
        return self
