"""Tests for EIT parser."""

import struct

from mpeg_ts_parser.eit import (
    parse_eit_event,
    parse_eit_section,
)


def create_eit_section(
    service_id: int = 0x0001,
    version_number: int = 0,
    table_id: int = 0x4E,
    events: list[dict] | None = None,
) -> bytes:
    """Create a minimal EIT section for testing."""
    if events is None:
        events = [
            {
                'event_id': 1425,
                'start_mjd': 0x1234,
                'start_bcd': bytes([0x09, 0x00, 0x00]),
                'duration_bcd': bytes([0x00, 0x30, 0x00]),
                'name': 'Test Programme',
            }
        ]
    
    events_data = b''
    for event in events:
        event_data = struct.pack('>H', event['event_id'])
        event_data += struct.pack('>H', event.get('start_mjd', 0x1234))
        event_data += event.get('start_bcd', bytes([0x09, 0x00, 0x00]))
        event_data += event.get('duration_bcd', bytes([0x00, 0x30, 0x00]))
        
        name = event.get('name', '')
        name_bytes = name.encode('iso-8859-1', errors='replace')
        short_event_desc = bytes([0x4D, 4 + len(name_bytes)])
        short_event_desc += b'eng'
        short_event_desc += bytes([len(name_bytes)])
        short_event_desc += name_bytes
        
        descriptors_length = len(short_event_desc)
        event_data += bytes([
            (0x00 << 5) | (0x00 << 4) | ((descriptors_length >> 8) & 0x0F)
        ])
        event_data += bytes([descriptors_length & 0xFF])
        event_data += short_event_desc
        
        events_data += event_data
    
    section_length = 11 + len(events_data) + 4
    
    header = bytes([
        table_id,
        0xB0 | ((section_length >> 8) & 0x0F),
        section_length & 0xFF,
        (service_id >> 8) & 0xFF,
        service_id & 0xFF,
        (version_number << 1) | 0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        table_id,
    ])
    
    return header + events_data + b'\x00' * 4


class TestParseEITSection:
    """Test EIT section parsing."""
    
    def test_present_following_section(self):
        events = [
            {
                'event_id': 1425,
                'start_mjd': 0x1234,
                'start_bcd': bytes([0x09, 0x00, 0x00]),
                'duration_bcd': bytes([0x00, 0x30, 0x00]),
                'name': 'Test Programme',
            },
            {
                'event_id': 1426,
                'start_mjd': 0x1234,
                'start_bcd': bytes([0x09, 0x30, 0x00]),
                'duration_bcd': bytes([0x00, 30, 0x00]),
                'name': 'Next Programme',
            }
        ]
        section = create_eit_section(events=events)
        result = parse_eit_section(section)
        
        assert result is not None
        assert result['table_id'] == 0x4E
        assert result['service_id'] == 0x0001
        assert result['current_next_indicator'] == 1
        assert len(result['events']) == 2
        assert result['events'][0]['event_id'] == 1425
        assert result['events'][0]['start_time'] == '09-00-00'
        assert result['events'][0]['duration'] == '00-30-00'
        assert result['events'][0]['name'] == 'Test Programme'
    
    def test_schedule_section(self):
        events = [
            {
                'event_id': 1500,
                'start_mjd': 0x1235,
                'start_bcd': bytes([0x10, 0x00, 0x00]),
                'duration_bcd': bytes([0x01, 0x00, 0x00]),
                'name': 'Schedule Event',
            }
        ]
        section = create_eit_section(table_id=0x4F, events=events)
        result = parse_eit_section(section)
        
        assert result is not None
        assert result['table_id'] == 0x4F
        assert len(result['events']) == 1
    
    def test_invalid_table_id(self):
        section = bytes([
            0x40, 0xB0, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ])
        result = parse_eit_section(section)
        assert result is None
    
    def test_truncated_section(self):
        section = bytes([0x4E, 0xB0, 0x10])
        result = parse_eit_section(section)
        assert result is None


class TestParseEITEvent:
    """Test individual EIT event parsing."""
    
    def test_event_with_name(self):
        event_data = struct.pack('>H', 1425)
        event_data += struct.pack('>H', 0x1234)
        event_data += bytes([0x09, 0x00, 0x00])
        event_data += bytes([0x00, 0x30, 0x00])
        
        name = 'Test Programme'
        name_bytes = name.encode('iso-8859-1')
        short_event_desc = bytes([0x4D, 4 + len(name_bytes)])
        short_event_desc += b'eng'
        short_event_desc += bytes([len(name_bytes)])
        short_event_desc += name_bytes
        
        descriptors_length = len(short_event_desc)
        event_data += bytes([
            (0x00 << 5) | (0x00 << 4) | ((descriptors_length >> 8) & 0x0F)
        ])
        event_data += bytes([descriptors_length & 0xFF])
        event_data += short_event_desc
        
        event, offset = parse_eit_event(event_data, 0, len(event_data))
        
        assert event is not None
        assert event['event_id'] == 1425
        assert event['start_time'] == '09-00-00'
        assert event['duration'] == '00-30-00'
        assert event['name'] == 'Test Programme'
    
    def test_event_without_name(self):
        event_data = struct.pack('>H', 1425)
        event_data += struct.pack('>H', 0x1234)
        event_data += bytes([0x09, 0x00, 0x00])
        event_data += bytes([0x00, 0x30, 0x00])
        
        descriptors_length = 0
        event_data += bytes([
            (0x00 << 5) | (0x00 << 4) | ((descriptors_length >> 8) & 0x0F)
        ])
        event_data += bytes([descriptors_length & 0xFF])
        
        event, offset = parse_eit_event(event_data, 0, len(event_data))
        
        assert event is not None
        assert event['event_id'] == 1425
        assert event['name'] is None
