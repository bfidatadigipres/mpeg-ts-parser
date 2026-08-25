"""Tests for utility functions: time conversion, folder path building."""

from datetime import datetime

from mpeg_ts_parser.utils import (
    bcd_to_int,
    bcd_to_time,
    build_folder_path,
    mjd_to_datetime,
    parse_short_event_descriptor,
)


class TestBCDConversion:
    """Test BCD to integer conversion."""
    
    def test_bcd_to_int(self):
        assert bcd_to_int(0x09) == 9
        assert bcd_to_int(0x30) == 30
        assert bcd_to_int(0x59) == 59
        assert bcd_to_int(0x00) == 0
        assert bcd_to_int(0x99) == 99
    
    def test_bcd_to_time(self):
        result = bcd_to_time(bytes([0x09, 0x00, 0x00]))
        assert result == '09-00-00'
        
        result = bcd_to_time(bytes([0x14, 0x30, 0x45]))
        assert result == '14-30-45'
        
        result = bcd_to_time(bytes([0x00, 0x00, 0x00]))
        assert result == '00-00-00'
    
    def test_bcd_to_time_invalid_length(self):
        result = bcd_to_time(bytes([0x09, 0x00]))
        assert result == '00-00-00'


class TestMJDConversion:
    """Test MJD date to datetime conversion."""
    
    def test_mjd_to_datetime(self):
        result = mjd_to_datetime(bytes([0x12, 0x34]))
        assert isinstance(result, datetime)
    
    def test_mjd_to_datetime_invalid_length(self):
        result = mjd_to_datetime(bytes([0x12]))
        assert isinstance(result, datetime)


class TestShortEventDescriptor:
    """Test short event descriptor parsing."""
    
    def test_parse_valid_descriptor(self):
        name = 'Test Programme'
        name_bytes = name.encode('iso-8859-1')
        data = b'eng' + bytes([len(name_bytes)]) + name_bytes
        
        result = parse_short_event_descriptor(data)
        assert result == 'Test Programme'
    
    def test_parse_empty_name(self):
        data = b'eng' + bytes([0])
        result = parse_short_event_descriptor(data)
        assert result == ''
    
    def test_parse_truncated_descriptor(self):
        data = b'eng'
        result = parse_short_event_descriptor(data)
        assert result is None
    
    def test_parse_short_data(self):
        data = b'en'
        result = parse_short_event_descriptor(data)
        assert result is None


class TestBuildFolderPath:
    """Test folder path building."""
    
    def test_string_format(self):
        event = {
            'start_time': '09-00-00',
            'event_id': 1425,
            'duration': '00-30-00',
        }
        result = build_folder_path(event, format='string')
        assert result == '09-00-00_1425_00-30-00'
    
    def test_list_format(self):
        event = {
            'start_time': '09-00-00',
            'event_id': 1425,
            'duration': '00-30-00',
        }
        result = build_folder_path(event, format='list')
        assert result == ['09-00-00', '1425', '00-30-00']
    
    def test_missing_fields(self):
        event = {}
        result = build_folder_path(event, format='string')
        assert result == '00-00-00_0_00-00-00'
    
    def test_default_format(self):
        event = {
            'start_time': '10-00-00',
            'event_id': 2000,
            'duration': '01-00-00',
        }
        result = build_folder_path(event)
        assert result == '10-00-00_2000_01-00-00'
