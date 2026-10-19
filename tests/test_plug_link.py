import hmac
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

from plug_link import PlugLink


def test_send_permit_packet_is_payload_plus_valid_hmac():
    secret = b"test-secret"
    link = PlugLink("127.0.0.1", 5055, secret)
    sent = []

    class FakeSocket:
        def sendto(self, packet, addr):
            sent.append((packet, addr))

    link._sock = FakeSocket()

    link.send_permit()

    (packet, addr) = sent[0]
    assert addr == ("127.0.0.1", 5055)
    assert len(packet) == 40
    seq, _ts = struct.unpack(">II", packet[:8])
    assert seq == 1
    assert hmac.new(secret, packet[:8], hashlib.sha256).digest() == packet[8:]


if __name__ == "__main__":
    test_send_permit_packet_is_payload_plus_valid_hmac()
    print("ok")
