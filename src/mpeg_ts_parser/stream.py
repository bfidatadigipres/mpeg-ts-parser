"""Stream readers for MPEG-TS data: RTP, UDP, file, HTTP."""

import logging
import socket
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

TS_PACKET_SIZE = 188
TS_SYNC_BYTE = 0x47
RTP_HEADER_MIN_SIZE = 12


def detect_and_strip_rtp(data: bytes) -> tuple[bytes, int]:
    """Detect and strip RTP header if present.
    
    Uses heuristic: first byte 0x80 (RTP version 2), second byte payload type 33.
    Header size: 12 + (csrc_count * 4).
    
    Args:
        data: Raw data potentially with RTP header
    
    Returns:
        Tuple of (stripped_data, header_size)
    """
    if len(data) < 2:
        return data, 0
    
    if (data[0] & 0xF0 == 0x80) and (data[1] & 0x7F == 33):
        csrc_count = data[0] & 0x0F
        header_size = RTP_HEADER_MIN_SIZE + (csrc_count * 4)
        logger.debug("RTP header detected, stripping %d bytes", header_size)
        return data[header_size:], header_size
    
    return data, 0


def parse_ts_header(data: bytes) -> dict | None:
    """Parse MPEG-TS packet header (4 bytes).
    
    Args:
        data: 4+ bytes starting with TS sync byte
    
    Returns:
        Header dict or None if invalid
    """
    if len(data) < 4 or data[0] != TS_SYNC_BYTE:
        return None
    
    byte1 = data[1]
    byte2 = data[2]
    byte3 = data[3]
    
    return {
        'sync_byte': data[0],
        'transport_error_indicator': (byte1 >> 7) & 0x01,
        'payload_unit_start_indicator': (byte1 >> 6) & 0x01,
        'transport_priority': (byte1 >> 5) & 0x01,
        'pid': ((byte1 & 0x1F) << 8) | byte2,
        'transport_scrambling_control': (byte3 >> 6) & 0x03,
        'adaptation_field_control': (byte3 >> 4) & 0x03,
        'continuity_counter': byte3 & 0x0F,
    }


class StreamBase(ABC):
    """Base class for MPEG-TS stream readers."""
    
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
    
    @abstractmethod
    def read_packets(self, count: int = 100) -> list[bytes]:
        """Read TS packets from stream.
        
        Args:
            count: Number of packets to read
        
        Returns:
            List of TS packet bytes
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the stream."""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class RTPStream(StreamBase):
    """RTP/UDP stream reader with automatic RTP header detection."""
    
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        super().__init__(timeout)
        self.host = host
        self.port = port
        self.socket: socket.socket | None = None
        self._buffer = b''
        self._connected = False
    
    def connect(self) -> None:
        """Open UDP socket for RTP stream."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(self.timeout)
        
        if self.host:
            self.socket.bind((self.host, self.port))
        else:
            self.socket.bind(('', self.port))
        
        self._connected = True
        logger.info("Connected to RTP stream on port %d", self.port)
    
    def read_packets(self, count: int = 100) -> list[bytes]:
        if not self._connected:
            self.connect()
        
        packets = []
        buffer = self._buffer
        
        while len(packets) < count:
            try:
                data = self.socket.recv(65535) if self.socket else b''
            except socket.timeout:
                logger.debug("Socket timeout while reading packets")
                break
            except OSError as e:
                logger.warning("Socket error: %s", e)
                break
            
            stripped, header_size = detect_and_strip_rtp(data)
            buffer += stripped
            
            while len(buffer) >= TS_PACKET_SIZE:
                if buffer[0] == TS_SYNC_BYTE:
                    packet = buffer[:TS_PACKET_SIZE]
                    buffer = buffer[TS_PACKET_SIZE:]
                    packets.append(packet)
                else:
                    buffer = buffer[1:]
                    logger.warning("Skipping byte: not TS sync byte")
        
        self._buffer = buffer
        return packets
    
    def close(self) -> None:
        if self.socket:
            self.socket.close()
            self.socket = None
        self._connected = False
        logger.debug("RTP stream closed")


class FileStream(StreamBase):
    """Local file reader with optional RTP header detection."""
    
    def __init__(self, file_path: str, timeout: float = 2.0):
        super().__init__(timeout)
        self.file_path = file_path
        self.file: BinaryIO | None = None
    
    def open(self) -> None:
        """Open the file."""
        path = Path(self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        self.file = open(path, 'rb')
        logger.info("Opened file: %s", self.file_path)
    
    def read_packets(self, count: int = 100) -> list[bytes]:
        if not self.file:
            self.open()
        
        packets = []
        buffer = b''
        
        while len(packets) < count:
            chunk = self.file.read(65535) if self.file else b''
            if not chunk:
                break
            
            stripped, _ = detect_and_strip_rtp(chunk)
            buffer += stripped
            
            while len(buffer) >= TS_PACKET_SIZE:
                if buffer[0] == TS_SYNC_BYTE:
                    packet = buffer[:TS_PACKET_SIZE]
                    buffer = buffer[TS_PACKET_SIZE:]
                    packets.append(packet)
                else:
                    buffer = buffer[1:]
                    logger.warning("Skipping byte: not TS sync byte")
        
        return packets
    
    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None
        logger.debug("File stream closed")


class HTTPStream(StreamBase):
    """HTTP stream reader for MPEG-TS over HTTP."""
    
    def __init__(self, url: str, timeout: float = 2.0):
        super().__init__(timeout)
        self.url = url
        self.socket: socket.socket | None = None
        self._buffer = b''
        self._connected = False
    
    def connect(self) -> None:
        """Open HTTP connection."""
        parsed = urlparse(self.url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 80
        path = parsed.path or '/'
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((host, port))
        
        request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        self.socket.sendall(request.encode())
        
        response = b''
        while b'\r\n\r\n' not in response:
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            response += chunk
        
        header_end = response.find(b'\r\n\r\n')
        if header_end != -1:
            self._buffer = response[header_end + 4:]
        
        self._connected = True
        logger.info("Connected to HTTP stream: %s", self.url)
    
    def read_packets(self, count: int = 100) -> list[bytes]:
        if not self._connected:
            self.connect()
        
        packets = []
        buffer = self._buffer
        
        while len(packets) < count:
            try:
                data = self.socket.recv(65535) if self.socket else b''
            except socket.timeout:
                logger.debug("Socket timeout while reading packets")
                break
            except OSError as e:
                logger.warning("Socket error: %s", e)
                break
            
            if not data:
                break
            
            stripped, _ = detect_and_strip_rtp(data)
            buffer += stripped
            
            while len(buffer) >= TS_PACKET_SIZE:
                if buffer[0] == TS_SYNC_BYTE:
                    packet = buffer[:TS_PACKET_SIZE]
                    buffer = buffer[TS_PACKET_SIZE:]
                    packets.append(packet)
                else:
                    buffer = buffer[1:]
                    logger.warning("Skipping byte: not TS sync byte")
        
        self._buffer = buffer
        return packets
    
    def close(self) -> None:
        if self.socket:
            self.socket.close()
            self.socket = None
        self._connected = False
        logger.debug("HTTP stream closed")


def create_stream(source: str, timeout: float = 2.0) -> StreamBase:
    """Create appropriate stream reader based on source URI.
    
    Args:
        source: URI or file path
        timeout: Socket timeout in seconds
    
    Returns:
        Stream reader instance
    
    Raises:
        ValueError: If source format is not supported
    """
    if source.startswith('rtp://'):
        parsed = urlparse(source)
        host = parsed.hostname or ''
        port = parsed.port
        if port is None:
            raise ValueError(f"RTP source must include port: {source}")
        return RTPStream(host, port, timeout)
    
    if source.startswith('udp://'):
        parsed = urlparse(source)
        host = parsed.hostname or ''
        port = parsed.port
        if port is None:
            raise ValueError(f"UDP source must include port: {source}")
        return RTPStream(host, port, timeout)
    
    if source.startswith('http://') or source.startswith('https://'):
        return HTTPStream(source, timeout)
    
    if Path(source).exists():
        return FileStream(source, timeout)
    
    raise ValueError(f"Unsupported source format: {source}")
