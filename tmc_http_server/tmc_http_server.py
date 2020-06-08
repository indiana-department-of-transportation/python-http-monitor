"""
.. py:module:: tmc_http_server
    :platform: *nix
    :synopsis: Defines a HTTP server designed for monitoring
        multithreaded Python3 applications. Altough we strive
        to be production-grade for the intended use case, this
        server is no meant to e.g. handle a RESTful API backend.
        The API is inspired by Flask.
"""
import re
import json

from typing import Union, Iterable, Dict, Tuple, Any
from ipaddress import IPv4Address
from threading import Thread
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import magic

# For those who don't like their data stringly-typed.
HOST = Union[str, IPv4Address]
VERBS = Union[str, Iterable[str]]
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

FIVE_HUNDRED = """
<h1>Internal Error 500:</h1>
<p>An error occured processing your request.</p>
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


def try_parse(value: Any):
    """Attempts to turn a string value into it's Python data
        representation via json.loads. Has special handling
        for strings 'True', 'False', and 'None'.

        :param value: The value. If a string, attempts to parse as
            JSON, if not or on parse error returns the value itself.
        :returns: The value.
    """

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if value == "True":
                return True

            if value == "False":
                return False

            if value == "None":
                return None

        return value

    try:
        return {key: try_parse(val) for key, val in value.items()}

    except AttributeError:
        return [try_parse(val) for val in value]

    except TypeError:
        return value


def unpack(value: Any):
    """If passed an iterable of exactly one element returns
        that element otherwise returns the argument. Attempts
        to recusively turn all JSON serialized values into
        python data.

        :param x: The putative iterable to unpack.
        :returns: The single item in the iterable or the argument.
    """

    if not isinstance(value, str):
        try:
            # Check if value is subscriptable.
            first = value[0]

            # Check if it only has the one element.
            if len(value) == 1:
                temp = try_parse(first)
                print("TEMP {}/{}".format(temp, type(temp)))
                return try_parse(first)

            return [unpack(item) for item in value]
        
        except KeyError:
            if value and value.items:  # Assume dict if non-empty
                return {key: unpack(val) for key, val in value.items()}

        except (TypeError, AttributeError):
            pass

    return try_parse(value)


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

    def handle_unknown_route(self, key: str) -> bool:
        """Handles requests we don't have a registered route for."""

        known = key in self.server.route_rules
        if not known:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(FOUR_OH_FOUR.encode())

        return known

    def handle_internal_error(self):
        """Returns a generic 500 response to the client."""

        self.send_response(500)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(FIVE_HUNDRED.encode())

    def guess_mime_type(self, string: str) -> str:
        """Attempts to guess the mime type of the result using
            libmagic.

            :param string: The string to infer the mime type for.
            :returns: Best guess as to the mime type.
        """

        return self.server.magic.from_buffer(string)

    def do_GET(self):
        """Handles HTTP GET requests by calling the function
            associated with that route.
        """

        path = self.path.split("?")[0]
        key = format_route_key(path, self.command)
        known = self.handle_unknown_route(key)
        if known:
            try:
                query_params = unpack(
                    parse_qs(urlparse(self.path).query)
                )

                result = self.server.route_rules[key](**query_params)
                mime_type = self.guess_mime_type(result)
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.end_headers()
                self.wfile.write(str(result).encode())

            except Exception as err:
                self.server.on_error(err)
                self.handle_internal_error()

    def do_POST(self):
        """Handles POST requests."""

        key = format_route_key(self.path, self.command)
        known = self.handle_unknown_route(key)
        if known:
            try:
                content_length = self.headers.get("Content-Length", 0)
                content_type = self.headers.get("Content-Type")
                print("CONTENT {} {}".format(content_type, content_length))

                # Here we'll try to handle the body if it's there based
                # on the content-type header if present. Currently we're
                # only handling url-encoded form data, json data, and plain text
                # because again, this is just a basic server for monitoring
                # a Python application.
                if "application/json" in content_type:
                    body = self.rfile.read(int(content_length)).decode("utf-8")
                    kwargs = json.loads(body) or {}
                    result = self.server.route_rules[key](**kwargs)

                elif content_type == "application/x-www-form-urlencoded":
                    body = self.rfile.read(int(content_length)).decode("utf-8")
                    print(body)
                    print(parse_qs(body))
                    query_params = unpack(
                        parse_qs(body)
                    )

                    print(query_params)

                    result = self.server.route_rules[key](**query_params)

                elif body:  # Assume it's a string and the handler will accept
                    result = self.server.route_rules[key](body)

                else:
                    result = self.server.route_rules[key]()

                mime_type = self.guess_mime_type(result)
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.end_headers()
                self.wfile.write(str(result).encode())

            except Exception as err:
                self.server.on_error(err)
                self.handle_internal_error()


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
        self.__magic = magic.Magic(mime=True)

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
                self.__magic,
                self.address,
                self.__handler,
                self.__on_error,
            ) as server:
            while self.__serving:
                try:
                    server.handle_request()
                except Exception as err:
                    self.__on_error(err)

            print("\nServer exited.\n")

    def stop(self):
        """Stops the HTTP server. Don't forget to call TMCServer::join
            afterwards if waiting on the thread to finish is necessary.
        """
        self.__serving = False
        return self


class TMCHTTPServer(ThreadingHTTPServer):
    """This is the actual HTTP server that is in turn wrapped by TMCServer.
        :param rules: The route rules registered with the parent server.
        :param magic_instance: The magic instance to check mime types against.
        :param address: Address tuple, defaults to quad zeros and port 8080.
        :param handler: The request handler, defaults to
            TMCRequestHandler.
        :param on_error: Because the actual HTTP server runs in
            a separate thread, the caller can pass a callback
            here to receive errors that arise during requests.
    """

    def __init__(
            self,
            rules,
            magic_instance,
            address: ADDRESS = ("0.0.0.0", 8080),
            handler=TMCRequestHandler,
            on_error=_default_error_handler,
        ):
        """Initializer for TMCHTTPServer"""

        super(TMCHTTPServer, self).__init__(address, handler)

        # These instance attributes are mostly here for the benefit of
        # the handler.
        self.magic = magic_instance
        self.route_rules = rules
        self.on_error = on_error
