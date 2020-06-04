import pytest
import requests
from unittest.mock import MagicMock
from .context import tmc_server

class TestBasicGet:
    def test_get(self):
        server = tmc_server.TMCServer()
        @server.route("/foobar")
        def foobar():
            return "foobar!"

        server.start()
        req = requests.get(
            "http://{}:{}/foobar".format(
                server.host, # default host, should be quad zeros
                server.port, # default port, should be 8080
            ),
            timeout=0.5,
        )

        server.stop()
        server.join(0.5)

        assert(req.text == "foobar!")
        assert(req.status_code == 200)

    def test_throws_on_duplicate_route(self):
        server = tmc_server.TMCServer()
        @server.route("/foobar")
        def foobar():
            return "foobar!"

        with pytest.raises(AssertionError):
            @server.route("/foobar")
            def barfoo():
                return "foobar!"

    def test_throws_on_route_add_while_running(self):
        server = tmc_server.TMCServer()
        @server.route("/foobar")
        def foobar():
            return "foobar!"

        server.start()
        with pytest.raises(AssertionError):
            @server.route("/barfoo")
            def barfoo():
                return "foobar!"

        server.stop()
        server.join(0.5)

    def test_throws_on_start_if_no_routes(self):
        on_error = MagicMock()

        server = tmc_server.TMCServer(
            on_error=on_error,
        )

        server.start()
        assert(on_error.call_count == 1)
        server.stop()
        server.join(0.5)

    def test_returns_four_oh_four_on_unknown_route(self):
        server = tmc_server.TMCServer()
        @server.route("/foobar")
        def foobar():
            return "foobar!"

        server.start()
        req = requests.get("http://{}:{}/barfoo".format(
            server.host,  # default host, should be quad zeros
            server.port,  # default port, should be 8080
        ))

        assert(req.status_code == 404)
        server.stop()
        server.join(0.5)
