"""A local SMTP sink for tests, standard library only (no Mailpit, no download): it speaks just enough
SMTP for smtplib (EHLO/HELO, MAIL, RCPT, DATA, RSET, NOOP, QUIT) and keeps every message it receives."""

from __future__ import annotations

import socketserver
import threading
from email import message_from_bytes, policy
from email.message import EmailMessage
from types import TracebackType


class _Handler(socketserver.StreamRequestHandler):
    server: _Server

    def _reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        self._reply("220 sink ready")
        rcpt: list[str] = []
        while line := self.rfile.readline():
            cmd = line.decode("utf-8", "replace").strip()
            verb = cmd.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self._reply("250 sink")
            elif verb == "MAIL":
                rcpt = []
                self._reply("250 ok")
            elif verb == "RCPT":
                rcpt.append(cmd.split(":", 1)[1].strip().strip("<>"))
                self._reply("250 ok")
            elif verb == "DATA":
                self._reply("354 end with <CRLF>.<CRLF>")
                data = bytearray()
                while (chunk := self.rfile.readline()) not in (b".\r\n", b""):
                    data += chunk[1:] if chunk.startswith(b"..") else chunk
                msg = message_from_bytes(bytes(data), policy=policy.default)
                assert isinstance(msg, EmailMessage)
                self.server.received.append((rcpt, msg))
                self._reply("250 queued")
            elif verb in ("RSET", "NOOP"):
                self._reply("250 ok")
            elif verb == "QUIT":
                self._reply("221 bye")
                return
            else:
                self._reply("502 not implemented")


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    received: list[tuple[list[str], EmailMessage]]


class SmtpSink:
    """`with SmtpSink() as sink:` listens on 127.0.0.1 at `sink.port`; `sink.messages` are what arrived."""

    def __init__(self) -> None:
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.received = []
        self.port: int = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def messages(self) -> list[tuple[list[str], EmailMessage]]:
        return self._server.received

    def __enter__(self) -> SmtpSink:
        self._thread.start()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._server.shutdown()
        self._server.server_close()


def text_part(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    assert part is not None
    return str(part.get_content())


def html_part(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("html",))
    assert part is not None
    return str(part.get_content())
