"""Tests for MPEG-TS stream readers and RTP header detection."""

import tempfile

import pytest

from mpeg_ts_parser.stream import (
    TS_PACKET_SIZE,
    TS_SYNC_BYTE,
    FileStream,
    detect_and_strip_rtp,
    parse_ts_header,
)


def create_ts_packet(
    pid: int = 0x0000,
    payload_unit_start: bool = False,
    payload: bytes = b'',
) -> bytes:
    """Create a minimal TS packet for testing."""
    byte1 = (
        (0x00 << 7)
        | (int(payload_unit_start) << 6)
        | (0x00 << 5)
        | ((pid >> 8) & 0x1F)
    )
    byte2 = pid & 0xFF
    byte3 = (0x01 << 4) | 0x00
    
    header = bytes([TS_SYNC_BYTE, byte1, byte2, byte3])
    full_payload = payload.ljust(TS_PACKET_SIZE - 4, b'\x00')
    return header + full_payload[:TS_PACKET_SIZE - 4]


class TestDetectAndStripRTP:
    """Test RTP header detection and stripping."""
    
    def test_no_rtp_header(self):
        data = bytes([TS_SYNC_BYTE, 0x40, 0x00, 0x10]) + b'\x00' * 184
        stripped, header_size = detect_and_strip_rtp(data)
        assert stripped == data
        assert header_size == 0
    
    def test_rtp_header_detected(self):
        rtp_header = bytes([
            0x80, 33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00
        ])
        ts_data = bytes([TS_SYNC_BYTE, 0x40, 0x00, 0x10]) + b'\x00' * 184
        data = rtp_header + ts_data
        
        stripped, size = detect_and_strip_rtp(data)
        assert stripped == ts_data
        assert size == 12
    
    def test_rtp_header_with_csrc(self):
        csrc_count = 2
        rtp_header = bytes([0x82, 33]) + b'\x00' * 10 + b'\x00' * (csrc_count * 4)
        ts_data = bytes([TS_SYNC_BYTE, 0x40, 0x00, 0x10]) + b'\x00' * 184
        data = rtp_header + ts_data
        
        stripped, size = detect_and_strip_rtp(data)
        assert stripped == ts_data
        assert size == 20
    
    def test_empty_data(self):
        stripped, size = detect_and_strip_rtp(b'')
        assert stripped == b''
        assert size == 0
    
    def test_short_data(self):
        data = bytes([0x80])
        stripped, size = detect_and_strip_rtp(data)
        assert stripped == data
        assert size == 0


class TestParseTSHeader:
    """Test TS packet header parsing."""
    
    def test_valid_header(self):
        packet = create_ts_packet(pid=0x0000)
        header = parse_ts_header(packet)
        
        assert header is not None
        assert header['sync_byte'] == TS_SYNC_BYTE
        assert header['pid'] == 0x0000
        assert header['payload_unit_start_indicator'] == 0
    
    def test_payload_unit_start(self):
        packet = create_ts_packet(pid=0x0000, payload_unit_start=True)
        header = parse_ts_header(packet)
        
        assert header is not None
        assert header['payload_unit_start_indicator'] == 1
    
    def test_invalid_sync_byte(self):
        packet = bytes([0x00, 0x40, 0x00, 0x10]) + b'\x00' * 184
        header = parse_ts_header(packet)
        assert header is None
    
    def test_short_packet(self):
        packet = bytes([TS_SYNC_BYTE, 0x40, 0x00])
        header = parse_ts_header(packet)
        assert header is None


class TestFileStream:
    """Test file-based stream reader."""
    
    def test_read_packets(self):
        packets = [
            create_ts_packet(pid=0x0000, payload_unit_start=True),
            create_ts_packet(pid=0x0100),
            create_ts_packet(pid=0x0012),
        ]
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ts') as f:
            f.write(b''.join(packets))
            f.flush()
            
            stream = FileStream(f.name)
            read_packets = stream.read_packets(3)
            stream.close()
            
            assert len(read_packets) == 3
            assert read_packets[0] == packets[0]
    
    def test_file_not_found(self):
        stream = FileStream("/nonexistent/file.ts")
        with pytest.raises(FileNotFoundError):
            stream.read_packets(1)
    
    def test_rtp_wrapped_file(self):
        rtp_header = bytes([0x80, 33]) + b'\x00' * 10
        ts_packet = create_ts_packet(pid=0x0000)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ts') as f:
            f.write(rtp_header + ts_packet)
            f.flush()
            
            stream = FileStream(f.name)
            read_packets = stream.read_packets(1)
            stream.close()
            
            assert len(read_packets) == 1
            assert read_packets[0] == ts_packet
