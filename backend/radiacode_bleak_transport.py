"""
Radiacode Bleak Bluetooth Transport

Cross-platform BLE transport for Radiacode devices using the bleak library.
This provides Windows/macOS support that the upstream radiacode library lacks.

References:
- https://github.com/cdump/radiacode (original bluepy implementation)
- https://bleak.readthedocs.io/
"""

import asyncio
import struct
import platform
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
import threading
import logging

logger = logging.getLogger(__name__)

# Radiacode BLE Service and Characteristic UUIDs
# From: https://github.com/cdump/radiacode/blob/master/src/radiacode/transports/bluetooth.py
SERVICE_UUID = "e63215e5-7003-49d8-96b0-b024798fb901"
WRITE_CHAR_UUID = "e63215e6-7003-49d8-96b0-b024798fb901"
NOTIFY_CHAR_UUID = "e63215e7-7003-49d8-96b0-b024798fb901"


class DeviceNotFound(Exception):
    """Raised when no Radiacode BLE device is found."""
    pass


class ConnectionClosed(Exception):
    """Raised when the BLE connection is closed unexpectedly."""
    pass


# Import bleak - available on all platforms
try:
    from bleak import BleakClient, BleakScanner
    from bleak.exc import BleakError
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False
    BleakClient = None
    BleakScanner = None
    BleakError = Exception


class BytesBuffer:
    """A buffer for reading binary data with position tracking.
    Matches the official radiacode library implementation.
    """
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def size(self) -> int:
        return len(self._data) - self._pos

    def remaining(self) -> int:
        """Alias for size() for backward compatibility if needed."""
        return self.size()

    def data(self) -> bytes:
        """Returns the remaining unread data."""
        return self._data[self._pos :]

    def unpack(self, fmt: str) -> tuple:
        sz = struct.calcsize(fmt)
        if self._pos + sz > len(self._data):
            raise ValueError(f'BytesBuffer: {sz} bytes required for {fmt}, but have only {len(self._data) - self._pos}')
        self._pos += sz
        return struct.unpack_from(fmt, self._data, self._pos - sz)

    def unpack_string(self) -> str:
        slen = self.unpack('<B')[0]
        return self.unpack(f'<{slen}s')[0].decode('ascii')


async def scan_for_radiacode_devices(timeout: float = 5.0) -> List[Dict[str, Any]]:
    """
    Scan for nearby Radiacode BLE devices.
    
    Args:
        timeout: Scan duration in seconds
        
    Returns:
        List of dicts with 'name', 'address', and 'rssi' for each found device
    """
    if not HAS_BLEAK:
        logger.error("bleak library not installed")
        return []
    
    devices = []
    try:
        logger.info(f"Starting BLE scan for {timeout}s...")
        discovered = await BleakScanner.discover(timeout=timeout)
        
        for device in discovered:
            # Radiacode devices have names like "RadiaCode-103", "RC-103", "RG-103", etc.
            name = device.name or ""
            if any(name.startswith(p) for p in ["RC-", "RG-", "RadiaCode-"]):
                devices.append({
                    "name": name,
                    "address": device.address,
                    "rssi": getattr(device, 'rssi', None)
                })
                logger.info(f"Found Radiacode device: {name} ({device.address})")
        
        # Also check for devices advertising the Radiacode service UUID
        for device in discovered:
            if device.address not in [d["address"] for d in devices]:
                # Check if device has the Radiacode service
                try:
                    if device.metadata.get("uuids") and SERVICE_UUID.lower() in [u.lower() for u in device.metadata.get("uuids", [])]:
                        devices.append({
                            "name": device.name or "Unknown Radiacode",
                            "address": device.address,
                            "rssi": getattr(device, 'rssi', None)
                        })
                        logger.info(f"Found Radiacode device by UUID: {device.name} ({device.address})")
                except Exception:
                    pass
                    
    except Exception as e:
        logger.error(f"BLE scan error: {e}")
    
    return devices


class BleakBluetooth:
    """
    Cross-platform BLE transport for Radiacode devices using bleak.
    
    Provides the same interface as the upstream radiacode library's Bluetooth class,
    but works on Windows and macOS in addition to Linux.
    """
    
    def __init__(self, mac: str, timeout: float = 10.0):
        """
        Initialize and connect to a Radiacode BLE device.
        
        Args:
            mac: Bluetooth MAC address or device identifier
            timeout: Connection timeout in seconds
        """
        if not HAS_BLEAK:
            raise ImportError("bleak library not installed. Run: pip install bleak")
        
        self._mac = mac
        self._timeout = timeout
        self._client: Optional[BleakClient] = None
        self._closing = False
        
        # Response handling
        self._resp_buffer = b''
        self._resp_size = 0
        self._response: Optional[bytes] = None
        self._response_event = threading.Event()
        
        # Background event loop management
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        
        # Connect synchronously using the background loop
        try:
            self._run_async(self._connect())
        except Exception as e:
            self.close()
            raise DeviceNotFound(f"Connection failed: {e}") from e
    
    def _run_event_loop(self):
        """Target for the background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def _run_async(self, coro):
        """Schedule a coroutine on the background thread and wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _connect(self):
        """Internal async connection logic."""
        logger.info(f"Connecting to Radiacode BLE device: {self._mac}")
        
        # On Windows, sometimes cached services cause issues
        client_kwargs = {"timeout": self._timeout}
        if platform.system() == 'Windows':
            # Use cached services can sometimes be problematic if services changed
            # but usually it's faster. Let's try default first.
            pass
            
        self._client = BleakClient(self._mac, **client_kwargs)
        
        # Try connecting with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"Connection attempt {attempt + 1}/{max_retries}...")
                connected = await self._client.connect()
                
                # On Windows, connect() might return False even if it worked or is already connected
                if not connected:
                    if self._client.is_connected:
                        logger.warning("connect() returned False but is_connected is True. Proceeding.")
                        connected = True
                
                if connected:
                    logger.info(f"Connected to {self._mac}")
                    
                    # Enable notifications on the notify characteristic
                    logger.debug(f"Starting notifications on {NOTIFY_CHAR_UUID}...")
                    await self._client.start_notify(NOTIFY_CHAR_UUID, self._notification_handler)
                    logger.info("Notifications enabled")
                    return
                
                logger.warning(f"Connection attempt {attempt + 1} failed (returned False)")
            except BleakError as e:
                logger.warning(f"Connection attempt {attempt + 1} raised error: {e}")
                if attempt == max_retries - 1:
                    raise DeviceNotFound(f"BLE connection error: {e}") from e
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2.0)
                
        raise DeviceNotFound(f"Failed to connect to {self._mac} after {max_retries} attempts")
    
    def _notification_handler(self, sender, data: bytearray):
        """
        Handle incoming BLE notifications.
        """
        data = bytes(data)
        logger.debug(f"BLE Received: {data.hex()}")
        
        if self._resp_size == 0:
            # First chunk - extract total size from header
            if len(data) < 4:
                logger.warning(f"Notification too short: {len(data)} bytes")
                return
            size_val = struct.unpack('<I', data[:4])[0]
            self._resp_size = 4 + size_val
            self._resp_buffer = data[4:]
            logger.debug(f"Response size: {self._resp_size}, First buffer: {self._resp_buffer.hex()}")
        else:
            # Continuation chunk
            self._resp_buffer += data
            logger.debug(f"Added chunk: {data.hex()}, Total buffer size: {len(self._resp_buffer)}")
        
        self._resp_size -= len(data)
        
        if self._resp_size <= 0:
            # Response complete
            self._response = self._resp_buffer
            self._resp_buffer = b''
            self._resp_size = 0
            self._response_event.set()
            logger.debug(f"Response complete: {self._response.hex() if self._response else 'None'}")
    
    def execute(self, req: bytes) -> BytesBuffer:
        """
        Send a command to the device and wait for response.
        
        Args:
            req: Command bytes to send
            
        Returns:
            BytesBuffer containing the response
        """
        if self._closing:
            raise ConnectionClosed("Connection is closing")
        
        if not self._client or not self._client.is_connected:
            raise ConnectionClosed("Not connected to device")
        
        # Reset response state
        self._response = None
        self._response_event.clear()
        
        async def _execute():
            # Send request in chunks of 20 bytes (BLE MTU limit)
            # Note: Radiacode original uses 18 bytes, but 20 is standard BLE
            chunk_size = 20
            for pos in range(0, len(req), chunk_size):
                chunk = req[pos:min(pos + chunk_size, len(req))]
                logger.debug(f"BLE Sending chunk: {chunk.hex()}")
                await self._client.write_gatt_char(WRITE_CHAR_UUID, chunk, response=True)
        
        try:
            self._run_async(_execute())
        except BleakError as e:
            raise ConnectionClosed(f"Write error: {e}") from e
        
        # Wait for response with timeout
        if not self._response_event.wait(timeout=10.0):
            raise TimeoutError("Response timeout")
        
        if self._closing:
            raise ConnectionClosed("Connection closed while waiting for response")
        
        return BytesBuffer(self._response)
    
    def close(self):
        """Disconnect from the BLE device and stop the background loop."""
        self._closing = True
        
        if self._client and self._client.is_connected:
            async def _disconnect():
                try:
                    await self._client.stop_notify(NOTIFY_CHAR_UUID)
                except Exception:
                    pass
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            
            try:
                self._run_async(_disconnect())
            except Exception:
                pass
        
        # Stop the event loop
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
            
        self._client = None
        logger.info("BLE connection closed")
    
    @property
    def is_connected(self) -> bool:
        """Check if still connected."""
        return self._client is not None and self._client.is_connected


def scan_radiacode_sync(timeout: float = 5.0) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for BLE device scanning.
    
    Args:
        timeout: Scan duration in seconds
        
    Returns:
        List of discovered Radiacode devices
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(scan_for_radiacode_devices(timeout))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return []
