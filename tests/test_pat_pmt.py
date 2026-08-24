"""Tests for PAT and PMT parsers."""

import struct

from mpeg_ts_parser.pat_pmt import (
    discover_eit_pid_from_pmt,
    parse_pat_payload,
    parse_pmt_payload,
)


def create_pat_section(
    transport_stream_id: int = 0x0001,
    version_number: int = 0,
    programmes: dict | None = None,
) -> bytes:
    """Create a minimal PAT section for testing."""
    if programmes is None:
        programmes = {1: 0x0100}
    
    section_data = b''
    for prog_num, pid in programmes.items():
        section_data += struct.pack('>H', prog_num)
        section_data += struct.pack('>H', 0xE000 | pid)
    
    section_length = 5 + len(section_data) + 4
    
    header = bytes([
        0x00,
        0xB0 | ((section_length >> 8) & 0x0F),
        section_length & 0xFF,
        (transport_stream_id >> 8) & 0xFF,
        transport_stream_id & 0xFF,
        (version_number << 1) | 0x01,
        0x00,
        0x00,
    ])
    
    return header + section_data + b'\x00' * 4


def create_pmt_section(
    programme_number: int = 1,
    version_number: int = 0,
    pcr_pid: int = 0x0100,
    elementary_streams: list[dict] | None = None,
) -> bytes:
    """Create a minimal PMT section for testing."""
    if elementary_streams is None:
        elementary_streams = [
            {'stream_type': 0x02, 'pid': 0x0100, 'descriptors': []},
            {'stream_type': 0x03, 'pid': 0x0101, 'descriptors': []},
        ]
    
    program_info_length = 0
    
    es_data = b''
    for es in elementary_streams:
        es_data += bytes([es['stream_type']])
        es_data += struct.pack('>H', 0xE000 | es['pid'])
        
        desc_data = b''
        for desc in es.get('descriptors', []):
            desc_data += bytes([desc['tag'], desc['length']])
            desc_data += desc.get('data', b'')
        
        es_data += struct.pack('>H', 0xF000 | len(desc_data))
        es_data += desc_data
    
    section_length = 9 + program_info_length + len(es_data) + 4
    
    header = bytes([
        0x02,
        0xB0 | ((section_length >> 8) & 0x0F),
        section_length & 0xFF,
        (programme_number >> 8) & 0xFF,
        programme_number & 0xFF,
        (version_number << 1) | 0x01,
        0x00,
        0x00,
        (pcr_pid >> 8) & 0xFF,
        pcr_pid & 0xFF,
        (program_info_length >> 8) & 0xFF,
        program_info_length & 0xFF,
    ])
    
    return header + es_data + b'\x00' * 4


class TestParsePATPayload:
    """Test PAT parsing."""
    
    def test_basic_pat(self):
        programmes = {1: 0x0100, 2: 0x0200}
        section = create_pat_section(programmes=programmes)
        pat = parse_pat_payload(section)
        
        assert pat is not None
        assert pat['table_id'] == 0x00
        assert pat['transport_stream_id'] == 0x0001
        assert pat['version_number'] == 0
        assert pat['current_next_indicator'] == 1
        assert pat['programmes'] == programmes
    
    def test_pat_with_network_pid(self):
        programmes = {0: 0x0010, 1: 0x0100}
        section = create_pat_section(programmes=programmes)
        pat = parse_pat_payload(section)
        
        assert pat is not None
        assert 0 in pat['programmes']
        assert 1 in pat['programmes']
    
    def test_truncated_pat(self):
        section = bytes([0x00, 0xB0, 0x10])
        pat = parse_pat_payload(section)
        assert pat is None
    
    def test_wrong_table_id(self):
        section = bytes([0x02, 0xB0, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
        pat = parse_pat_payload(section)
        assert pat is None


class TestParsePMTPayload:
    """Test PMT parsing."""
    
    def test_basic_pmt(self):
        elementary_streams = [
            {'stream_type': 0x02, 'pid': 0x0100, 'descriptors': []},
            {'stream_type': 0x03, 'pid': 0x0101, 'descriptors': []},
        ]
        section = create_pmt_section(
            programme_number=1,
            elementary_streams=elementary_streams,
        )
        pmt = parse_pmt_payload(section)
        
        assert pmt is not None
        assert pmt['table_id'] == 0x02
        assert pmt['programme_number'] == 1
        assert pmt['pcr_pid'] == 0x0100
        assert len(pmt['elementary_streams']) == 2
        assert pmt['elementary_streams'][0]['stream_type'] == 0x02
        assert pmt['elementary_streams'][0]['elementary_pid'] == 0x0100
    
    def test_pmt_with_eit_descriptor(self):
        eit_descriptor = {
            'tag': 0x4A,
            'length': 4,
            'data': bytes([0x01, 0x02, 0x03, 0x04]),
        }
        elementary_streams = [
            {
                'stream_type': 0x06,
                'pid': 0x0012,
                'descriptors': [eit_descriptor],
            },
        ]
        section = create_pmt_section(elementary_streams=elementary_streams)
        pmt = parse_pmt_payload(section)
        
        assert pmt is not None
        assert len(pmt['elementary_streams']) == 1
        assert pmt['elementary_streams'][0]['descriptors'][0]['tag'] == 0x4A
    
    def test_truncated_pmt(self):
        section = bytes([0x02, 0xB0, 0x10])
        pmt = parse_pmt_payload(section)
        assert pmt is None
    
    def test_wrong_table_id(self):
        section = bytes([
            0x00, 0xB0, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ])
        pmt = parse_pmt_payload(section)
        assert pmt is None


class TestDiscoverEITPID:
    """Test EIT PID discovery from PMT."""
    
    def test_discover_eit_pid(self):
        eit_descriptor = {
            'tag': 0x4A,
            'length': 4,
            'data': bytes([0x01, 0x02, 0x03, 0x04]),
        }
        elementary_streams = [
            {
                'stream_type': 0x06,
                'pid': 0x0012,
                'descriptors': [eit_descriptor],
            },
        ]
        section = create_pmt_section(elementary_streams=elementary_streams)
        pmt = parse_pmt_payload(section)
        
        assert pmt is not None
        eit_pid = discover_eit_pid_from_pmt(pmt)
        assert eit_pid == 0x0012
    
    def test_no_eit_descriptor(self):
        elementary_streams = [
            {'stream_type': 0x02, 'pid': 0x0100, 'descriptors': []},
        ]
        section = create_pmt_section(elementary_streams=elementary_streams)
        pmt = parse_pmt_payload(section)
        
        assert pmt is not None
        eit_pid = discover_eit_pid_from_pmt(pmt)
        assert eit_pid is None
