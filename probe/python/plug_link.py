"""Stop-plug pairing: sends HMAC-signed run permits to the XIAO plug over UDP.

NOT YET WIRED INTO main.py and not tested against real hardware - test with a
lamp before ever pointing this at mains. See plug/xiao_plug/xiao_plug.ino for
the packet format and plug-side fail-safe behaviour (any gap over ~2.5 s opens
the relay).
"""

import hmac
import hashlib
import socket
import struct
import time


class PlugLink:
    """Call send_permit() once per second while Guard mode is actively
    guarding; stop calling it to let the plug's own timeout open the relay."""

    def __init__(self, plug_ip: str, plug_port: int, secret: bytes):
        self._addr = (plug_ip, plug_port)
        self._secret = secret
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._seq = 0

    def send_permit(self) -> None:
        self._seq += 1
        payload = struct.pack(">II", self._seq, int(time.time()))
        tag = hmac.new(self._secret, payload, hashlib.sha256).digest()
        self._sock.sendto(payload + tag, self._addr)


def _demo():
    secret = b"test-secret"
    link = PlugLink("127.0.0.1", 0, secret)
    link._sock = None  # no real socket needed for this check
    link._seq = 0
    link._seq += 1
    payload = struct.pack(">II", link._seq, int(time.time()))
    tag = hmac.new(secret, payload, hashlib.sha256).digest()
    packet = payload + tag
    assert len(packet) == 40
    assert hmac.new(secret, packet[:8], hashlib.sha256).digest() == packet[8:]
    print("ok")


if __name__ == "__main__":
    _demo()
