"""Offline stand-in for the Anthropic Messages API, for real-binary E2E tests.

A `claude -p` run needs one model turn to complete. FakeAnthropicServer
records the JSON body of every POST /v1/messages request and answers one
assistant text turn, so the binary exits normally and the test can inspect
exactly what it sent: the system prompt, the loaded skills, agents, commands,
rules and output style, and the resumed conversation history.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from collections.abc import Iterable
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler
from wsgiref.simple_server import WSGIServer
from wsgiref.simple_server import make_server

FAKE_REPLY = 'FAKE-OK'

_WSGIResponse = Callable[[str, list[tuple[str, str]]], Any]


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _QuietHandler(WSGIRequestHandler):
    def log_request(self, code: int | str = '-', size: int | str = '-') -> None:
        del code, size


class FakeAnthropicServer:
    """Record every Messages request and answer one text turn.

    The turn is streamed as SSE when the request asks for streaming and sent
    as plain JSON otherwise. POST /v1/messages/count_tokens returns a fixed
    count; every other request is 404 and is never recorded.
    """

    def __init__(self, reply_text: str = FAKE_REPLY) -> None:
        self.reply_text = reply_text
        self.bodies: list[dict[str, Any]] = []
        self._server = make_server(
            '127.0.0.1', 0, self._app, server_class=_ThreadingWSGIServer, handler_class=_QuietHandler,
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self._server.server_address[1]}'

    def start(self) -> FakeAnthropicServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _app(self, environ: dict[str, Any], start_response: _WSGIResponse) -> Iterable[bytes]:
        if environ.get('REQUEST_METHOD') != 'POST':
            return self._respond(start_response, '404 Not Found', 'text/plain', b'not found')
        path = environ.get('PATH_INFO', '')
        length = int(environ.get('CONTENT_LENGTH') or 0)
        raw = environ['wsgi.input'].read(length) if length else b''
        if path.startswith('/v1/messages/count_tokens'):
            return self._respond_json(start_response, {'input_tokens': 42})
        if path.startswith('/v1/messages'):
            body = json.loads(raw)
            self.bodies.append(body)
            if body.get('stream'):
                return self._respond(start_response, '200 OK', 'text/event-stream', self._sse_payload())
            return self._respond_json(start_response, self._message_json(body.get('model', 'fake')))
        return self._respond(start_response, '404 Not Found', 'text/plain', b'not found')

    @staticmethod
    def _respond(start_response: _WSGIResponse, status: str, content_type: str, data: bytes) -> list[bytes]:
        start_response(status, [('Content-Type', content_type), ('Content-Length', str(len(data)))])
        return [data]

    def _respond_json(self, start_response: _WSGIResponse, payload: dict[str, Any]) -> list[bytes]:
        return self._respond(start_response, '200 OK', 'application/json', json.dumps(payload).encode('utf-8'))

    def _message_json(self, model: str) -> dict[str, Any]:
        return {
            'id': 'msg_fake', 'type': 'message', 'role': 'assistant', 'model': model,
            'content': [{'type': 'text', 'text': self.reply_text}],
            'stop_reason': 'end_turn', 'stop_sequence': None,
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }

    def _sse_payload(self) -> bytes:
        events: list[tuple[str, dict[str, Any]]] = [
            ('message_start', {'type': 'message_start', 'message': {
                'id': 'msg_fake', 'type': 'message', 'role': 'assistant', 'model': 'fake',
                'content': [], 'stop_reason': None, 'stop_sequence': None,
                'usage': {'input_tokens': 1, 'output_tokens': 0},
            }}),
            ('content_block_start', {
                'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''},
            }),
            ('content_block_delta', {
                'type': 'content_block_delta', 'index': 0,
                'delta': {'type': 'text_delta', 'text': self.reply_text},
            }),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {
                'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None},
                'usage': {'output_tokens': 1},
            }),
            ('message_stop', {'type': 'message_stop'}),
        ]
        return ''.join(f'event: {name}\ndata: {json.dumps(data)}\n\n' for name, data in events).encode('utf-8')
