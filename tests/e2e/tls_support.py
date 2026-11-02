"""HTTPS fixtures for the E2E tests of certificate verification.

Builds certificates with the cryptography package -- a self-signed one for
127.0.0.1, or a test certificate authority and a 127.0.0.1 certificate it
issues -- and serves files the way a GitLab instance serves a private
project through its REST API: a request without the project's token gets
404, as GitLab answers for a project the caller cannot see, and a request
with the token gets the file. Every request is recorded.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
import ssl
import threading
import urllib.parse
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from typing import Self
from wsgiref.simple_server import WSGIRequestHandler
from wsgiref.simple_server import WSGIServer
from wsgiref.simple_server import make_server

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID
from cryptography.x509.oid import NameOID

LOCALHOST = '127.0.0.1'
PROJECT = 'team/configs'
REF = 'main'

_PROJECT_FILES = f'/api/v4/projects/{PROJECT}/repository/files/'
_WSGIResponse = Callable[[str, list[tuple[str, str]]], Any]


@dataclass(frozen=True)
class CertificateFiles:
    """PEM files of a certificate and its private key."""

    certificate: Path
    key: Path


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _write(directory: Path, stem: str, certificate: x509.Certificate, key: rsa.RSAPrivateKey) -> CertificateFiles:
    directory.mkdir(parents=True, exist_ok=True)
    files = CertificateFiles(directory / f'{stem}.pem', directory / f'{stem}.key')
    files.certificate.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    files.key.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption(),
    ))
    return files


def _server_certificate(
    subject_key: rsa.RSAPrivateKey,
    issuer: x509.Name,
    issuer_key: rsa.RSAPrivateKey,
    issuer_identifier: x509.SubjectKeyIdentifier,
) -> x509.Certificate:
    """A certificate for 127.0.0.1 that macOS, Windows and OpenSSL accept for a TLS server."""
    now = dt.datetime.now(dt.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(_name(LOCALHOST))
        .issuer_name(issuer)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(LOCALHOST))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(issuer_identifier), critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def self_signed_server_certificate(directory: Path) -> CertificateFiles:
    """Write a self-signed certificate for 127.0.0.1, which no trust store holds.

    Returns:
        The certificate and key files.
    """
    key = _key()
    identifier = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    return _write(directory, 'self-signed', _server_certificate(key, _name(LOCALHOST), key, identifier), key)


@dataclass(frozen=True)
class CertificateAuthority:
    """A certificate authority made for one test run, and the 127.0.0.1 certificate it issued."""

    name: str
    authority: CertificateFiles
    server: CertificateFiles

    @property
    def fingerprint(self) -> str:
        """The SHA-1 fingerprint of the authority's certificate in upper-case hex, as the OS tools name it."""
        certificate = x509.load_pem_x509_certificate(self.authority.certificate.read_bytes())
        return certificate.fingerprint(hashes.SHA1()).hex().upper()


def make_certificate_authority(directory: Path, name: str) -> CertificateAuthority:
    """Write a certificate authority named ``name`` and a 127.0.0.1 certificate it issued.

    Returns:
        The authority and server files.
    """
    now = dt.datetime.now(dt.UTC)
    authority_key = _key()
    authority_identifier = x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key())
    authority = (
        x509.CertificateBuilder()
        .subject_name(_name(name))
        .issuer_name(_name(name))
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(authority_identifier, critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    server_key = _key()
    server = _server_certificate(server_key, authority.subject, authority_key, authority_identifier)
    return CertificateAuthority(
        name,
        _write(directory, 'authority', authority, authority_key),
        _write(directory, 'server', server, server_key),
    )


@dataclass(frozen=True)
class RecordedRequest:
    """One request the server answered."""

    method: str
    file: str
    token: str | None
    status: int


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """A WSGI server over TLS that runs each handshake in the connection's own thread.

    A real server handshakes with every client concurrently; a handshake in
    the accepting thread would stall every other connection behind a client
    that has connected and not yet sent its hello. A client that rejects the
    certificate closes the connection during or right after the handshake,
    which is expected here and prints no traceback.
    """

    daemon_threads = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tls: ssl.SSLContext | None = None

    def finish_request(self, request: object, client_address: object) -> None:
        assert self.tls is not None
        assert isinstance(request, socket.socket)
        with self.tls.wrap_socket(request, server_side=True) as connection:
            super().finish_request(connection, client_address)

    def handle_error(self, request: object, client_address: object) -> None:
        del request, client_address


class _QuietHandler(WSGIRequestHandler):
    def log_request(self, code: int | str = '-', size: int | str = '-') -> None:
        del code, size


class GitLabLikeServer:
    """An HTTPS server answering GitLab REST API file requests of one private project.

    Files live under PROJECT at REF. A request carrying the token in
    PRIVATE-TOKEN gets the file (HEAD and GET alike, a Range header ignored);
    any other request gets 404, the answer GitLab gives for a private project.
    The server listens on 127.0.0.1. The TLS context is built when the
    server is created, so a test creates the server before main() points
    ssl.SSLContext at the operating system's trust store; a server context of
    the trust store's class would verify the clients, which send no
    certificate.
    """

    def __init__(self, certificate: CertificateFiles, files: dict[str, bytes], token: str) -> None:
        self.files = files
        self.token = token
        self.requests: list[RecordedRequest] = []
        self._lock = threading.Lock()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate.certificate), str(certificate.key))
        self._server = make_server(
            LOCALHOST, 0, self._app, server_class=_ThreadingWSGIServer, handler_class=_QuietHandler,
        )
        self._server.tls = context
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def url(self, file_path: str) -> str:
        """The GitLab API URL of a file of the project, the form the setup derives for relative paths."""
        project = urllib.parse.quote(PROJECT, safe='')
        encoded = urllib.parse.quote(file_path, safe='')
        return f'https://{LOCALHOST}:{self.port}/api/v4/projects/{project}/repository/files/{encoded}/raw?ref={REF}'

    def requests_for(self, file_path: str) -> list[RecordedRequest]:
        """The recorded requests of one file, in order."""
        with self._lock:
            return [request for request in self.requests if request.file == file_path]

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)

    def _app(self, environ: dict[str, Any], start_response: _WSGIResponse) -> Iterable[bytes]:
        method = str(environ.get('REQUEST_METHOD'))
        path = str(environ.get('PATH_INFO', ''))
        token = environ.get('HTTP_PRIVATE_TOKEN')
        file_path = path[len(_PROJECT_FILES):-len('/raw')] if path.startswith(_PROJECT_FILES) and path.endswith('/raw') else ''
        content = self.files.get(file_path)
        status, body = '404 Not Found', b'{"message":"404 Project Not Found"}'
        if (
            content is not None
            and token == self.token
            and urllib.parse.parse_qs(str(environ.get('QUERY_STRING', ''))).get('ref') == [REF]
        ):
            status, body = '200 OK', content
        with self._lock:
            self.requests.append(RecordedRequest(method, file_path, token, int(status.split()[0])))
        start_response(status, [('Content-Type', 'application/octet-stream'), ('Content-Length', str(len(body)))])
        return [b''] if method == 'HEAD' else [body]
