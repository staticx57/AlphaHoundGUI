"""
BLE scan for Radiacode devices, against bleak's own data classes (BLEDevice, AdvertisementData).

BLEDevice.rssi and BLEDevice.metadata were removed from bleak; the signal strength and the advertised service UUIDs live in the
AdvertisementData that discover(return_adv=True) returns. The scan used to read the removed attributes, so RSSI was always None
and a device whose name is not "RadiaCode-..." was never found by its service UUID.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("bleak")
from bleak.backends.device import BLEDevice          # noqa: E402
from bleak.backends.scanner import AdvertisementData  # noqa: E402

import radiacode_bleak_transport as transport         # noqa: E402


def device(address, name):
    return BLEDevice(address, name, {})


def advertisement(name, rssi, uuids=()):
    return AdvertisementData(name, {}, {}, list(uuids), None, rssi, ())


class FakeScanner:
    found = {}

    @classmethod
    async def discover(cls, timeout=5.0, *, return_adv=False, **kwargs):
        assert return_adv, "the scan must ask for advertisement data: rssi and service UUIDs are not on the device object"
        return dict(cls.found)


@pytest.fixture
def scanner(monkeypatch):
    monkeypatch.setattr(transport, "BleakScanner", FakeScanner)
    monkeypatch.setattr(transport, "HAS_BLEAK", True)
    return FakeScanner


def scan():
    return asyncio.run(transport.scan_for_radiacode_devices(timeout=0.01))


def test_named_devices_are_found_with_their_signal_strength(scanner):
    scanner.found = {
        "52:43:06:E0:06:39": (device("52:43:06:E0:06:39", "RadiaCode-110"), advertisement("RadiaCode-110", -58)),
        "11:22:33:44:55:66": (device("11:22:33:44:55:66", "JBL Speaker"), advertisement("JBL Speaker", -40)),
        "AA:BB:CC:DD:EE:FF": (device("AA:BB:CC:DD:EE:FF", "RC-103G"), advertisement("RC-103G", -71)),
    }
    found = scan()
    assert sorted(d["name"] for d in found) == ["RC-103G", "RadiaCode-110"]
    assert {d["address"]: d["rssi"] for d in found} == {"52:43:06:E0:06:39": -58, "AA:BB:CC:DD:EE:FF": -71}


def test_a_device_is_found_by_its_service_uuid_when_its_name_is_not_recognised(scanner):
    scanner.found = {
        "01:02:03:04:05:06": (device("01:02:03:04:05:06", "My detector"), advertisement("My detector", -66, [transport.SERVICE_UUID.upper()])),
        "07:08:09:0A:0B:0C": (device("07:08:09:0A:0B:0C", None), advertisement(None, -80, [transport.SERVICE_UUID])),
        "0D:0E:0F:10:11:12": (device("0D:0E:0F:10:11:12", "Other"), advertisement("Other", -50, ["0000180f-0000-1000-8000-00805f9b34fb"])),
    }
    found = scan()
    assert {d["address"] for d in found} == {"01:02:03:04:05:06", "07:08:09:0A:0B:0C"}
    assert {d["name"] for d in found} == {"My detector", "Unknown Radiacode"}


def test_nothing_nearby_gives_an_empty_list_and_a_scan_error_does_not_raise(scanner, monkeypatch):
    scanner.found = {}
    assert scan() == []

    async def broken(cls, timeout=5.0, **kwargs):
        raise OSError("bluetooth is off")
    monkeypatch.setattr(FakeScanner, "discover", classmethod(broken))
    assert scan() == []
