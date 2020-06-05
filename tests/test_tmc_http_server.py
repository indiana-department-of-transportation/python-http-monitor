import pytest
import json
import requests
from unittest.mock import MagicMock
from .context import tmc_server


class TestServer:
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
        server.stop()
        server.join(0.5)
        assert(on_error.call_count == 1)


class TestGet:
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
        assert req.text == "foobar!"
    
    def test_get_with_qs(self):
        server = tmc_server.TMCServer(port=8081)
        @server.route("/foobar")
        def foobar(foo, bar):
            return str(foo) + str(bar)

        server.start()
        req = requests.get(
            "http://{}:{}/foobar?foo=3&bar=true".format(
                server.host,  # default host, should be quad zeros
                server.port,  # default port, should be 8080
            ),
            timeout=0.5,
        )

        
        server.stop()
        server.join(0.5)
        assert req.text == "3True"
    
    def test_returns_four_oh_four_on_unknown_route(self):
        server = tmc_server.TMCServer(port=8082)
        @server.route("/foobar")
        def foobar():
            return "foobar!"

        server.start()
        req = requests.get("http://{}:{}/barfoo".format(
            server.host,  # default host, should be quad zeros
            server.port,  # default port, should be 8080
        ))

        server.stop()
        server.join(0.5)
        assert(req.status_code == 404)


class TestBasicPost:
    def test_form_post(self):
        server = tmc_server.TMCServer(port=8083)
        @server.route("/foobar", methods=["POST"])
        def foobar(foo, bar):
            return json.dumps({
                "foo": foo,
                "bar": bar,
            })

        server.start()
        req = requests.post(
            url="http://{}:{}/foobar".format(
                server.host,  # default host, should be quad zeros
                server.port,  # default port, should be 8080
            ),
            data={
                "foo": 3,
                "bar": True,
            },
            
        )

        result = req.json()
        server.stop()
        server.join(0.5)
        assert result["foo"] == 3
        assert result["bar"] == True

    def test_json_post(self):
        server = tmc_server.TMCServer(port=8084)
        @server.route("/foobar", methods=["POST"])
        def foobar(foo, bar):
            return json.dumps({
                "foo": foo,
                "bar": bar,
            })

        server.start()
        req = requests.post(
            url="http://{}:{}/foobar".format(
                server.host,  # default host, should be quad zeros
                server.port,  # default port, should be 8080
            ),
            json={
                "foo": 3,
                "bar": True
            },
        )

        result = req.json()
        server.stop()
        server.join(0.5)
        assert result["foo"] == 3
        assert result["bar"] == True

    def test_plain_text_post(self):
        server = tmc_server.TMCServer(port=8085)
        @server.route("/barfoo", methods=["POST"])
        def foobar(foo, bar):
            return str(foo) + str(bar)

        server.start()
        req = requests.post(
            url="http://{}:{}/barfoo".format(
                server.host,  # default host, should be quad zeros
                server.port,  # default port, should be 8080
            ),
            json={
                "foo": 3,
                "bar": True
            },
        )

        server.stop()
        server.join(0.5)
        assert req.text == "3True"

    def test_returns_four_oh_four_on_unknown_route(self):
        server = tmc_server.TMCServer(port=8086)
        @server.route("/foobar", methods=["POST"])
        def foobar():
            return "foobar!"

        server.start()
        req = requests.get("http://{}:{}/foobar".format(
            server.host,  # default host, should be quad zeros
            server.port,  # default port, should be 8080
        ))

        server.stop()
        server.join(0.5)
        assert(req.status_code == 404)
