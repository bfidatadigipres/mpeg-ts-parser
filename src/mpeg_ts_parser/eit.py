"""EIT parser for DVB present/following and schedule events."""

import logging

from mpeg_ts_parser.pat_pmt import find_pat, get_eit_pid
from mpeg_ts_parser.stream import StreamBase, parse_ts_header
from mpeg_ts_parser.utils import (
    bcd_to_time,
    parse_short_event_descriptor,
)

logger = logging.getLogger(__name__)

TS_PACKET_SIZE = 188
EIT_TABLE_ID_PRESENT_FOLLOWING = 0x4E
EIT_TABLE_ID_SCHEDULE_START = 0x4F
EIT_TABLE_ID_SCHEDULE_END = 0x5F
EIT_PID_STANDARD = 0x0012
SHORT_EVENT_DESCRIPTOR = 0x4D


def parse_eit_event(
    data: bytes,
    offset: int,
    end_offset: int,
) -> tuple[dict | None, int]:
    """Parse a single EIT event from data.
    
    Args:
        data: EIT section data
        offset: Current offset in data
        end_offset: End of event loop
    
    Returns:
        Tuple of (event_dict, new_offset)
    """
    if offset + 12 > end_offset:
        return None, offset
    
    event_id = (data[offset] << 8) | data[offset + 1]
    start_bcd = data[offset + 4:offset + 7]
    duration_bcd = data[offset + 7:offset + 10]
    running_status = (data[offset + 10] >> 5) & 0x07
    free_ca_mode = (data[offset + 10] >> 4) & 0x01
    descriptors_length = ((data[offset + 10] & 0x0F) << 8) | data[offset + 11]
    
    offset += 12
    
    start_time = bcd_to_time(start_bcd)
    duration = bcd_to_time(duration_bcd)
    
    event_name = None
    desc_end = offset + descriptors_length
    
    while offset + 2 <= desc_end:
        desc_tag = data[offset]
        desc_length = data[offset + 1]
        
        if offset + 2 + desc_length > desc_end:
            logger.warning("EIT descriptor truncated")
            break
        
        if desc_tag == SHORT_EVENT_DESCRIPTOR:
            event_name = parse_short_event_descriptor(
                data[offset + 2:offset + 2 + desc_length]
            )
        
        offset += 2 + desc_length
    
    return {
        'event_id': event_id,
        'start_time': start_time,
        'duration': duration,
        'name': event_name,
        'running_status': running_status,
        'free_ca_mode': free_ca_mode,
    }, offset


def parse_eit_section(data: bytes) -> dict | None:
    """Parse EIT section payload.
    
    Args:
        data: EIT section data (after pointer field)
    
    Returns:
        EIT dict with events, or None
    """
    if len(data) < 11:
        return None
    
    table_id = data[0]
    
    if (
        table_id < EIT_TABLE_ID_PRESENT_FOLLOWING
        or table_id > EIT_TABLE_ID_SCHEDULE_END
    ):
        return None
    
    section_length = ((data[1] & 0x0F) << 8) | data[2]
    
    if len(data) < 3 + section_length:
        logger.warning("EIT section truncated")
        return None
    
    service_id = (data[3] << 8) | data[4]
    version_number = (data[5] >> 1) & 0x1F
    current_next_indicator = data[5] & 0x01
    section_number = data[6]
    last_section_number = data[7]
    transport_stream_id = (data[8] << 8) | data[9]
    original_network_id = (data[10] << 8) | data[11]
    
    events = []
    offset = 14
    section_end = 3 + section_length - 4
    
    while offset < section_end:
        event, offset = parse_eit_event(data, offset, section_end)
        if event:
            events.append(event)
    
    return {
        'table_id': table_id,
        'service_id': service_id,
        'version_number': version_number,
        'current_next_indicator': current_next_indicator,
        'section_number': section_number,
        'last_section_number': last_section_number,
        'transport_stream_id': transport_stream_id,
        'original_network_id': original_network_id,
        'events': events,
    }


def find_eit_packets(
    stream: StreamBase,
    eit_pid: int,
    max_packets: int = 5000,
    timeout: float = 2.0,
) -> list[bytes]:
    """Find EIT packets from stream and reassemble sections.
    
    Handles multi-packet section reassembly based on section_length field.
    For network streams (RTP/UDP/HTTP), reads until EIT found or timeout.
    For file streams, reads sequentially from current position.
    
    Args:
        stream: Stream reader
        eit_pid: EIT PID
        max_packets: Maximum packets to scan (file streams only)
        timeout: Maximum time to wait (network streams only)
    
    Returns:
        List of complete EIT section payloads
    """
    if hasattr(stream, 'read_until_eit'):
        return stream.read_until_eit(eit_pid, timeout=timeout)
    
    packets = stream.read_packets(max_packets)
    eit_sections = []
    
    section_buffer = b''
    in_section = False
    expected_length = 0
    
    for packet in packets:
        header = parse_ts_header(packet)
        if header is None:
            continue
        
        if header['pid'] != eit_pid:
            continue
        
        payload_start = 4
        if header['adaptation_field_control'] in (2, 3):
            if header['adaptation_field_control'] == 2:
                continue
            if len(packet) > 4:
                adaptation_length = packet[4]
                payload_start = 5 + adaptation_length
        
        if payload_start >= TS_PACKET_SIZE:
            continue
        
        payload = packet[payload_start:]
        if len(payload) == 0:
            continue
        
        if header['payload_unit_start_indicator']:
            pointer_field = payload[0]
            section_data = payload[1 + pointer_field:]
            
            if in_section and len(section_buffer) >= expected_length:
                eit_sections.append(section_buffer[:expected_length])
            
            if len(section_data) >= 3:
                section_length = ((section_data[1] & 0x0F) << 8) | section_data[2]
                expected_length = 3 + section_length
                section_buffer = section_data
                in_section = True
            else:
                in_section = False
                section_buffer = b''
        else:
            if in_section:
                section_buffer += payload
        
        if in_section and len(section_buffer) >= expected_length:
            eit_sections.append(section_buffer[:expected_length])
            section_buffer = b''
            in_section = False
    
    if in_section and len(section_buffer) >= expected_length:
        eit_sections.append(section_buffer[:expected_length])
    
    logger.info("Found %d complete EIT sections", len(eit_sections))
    return eit_sections


def parse_eit_present_following(
    stream: StreamBase,
    eit_pid: int | None = None,
    timeout: float = 2.0,
    schedule_timeout: float = 5.0,
) -> dict:
    """Parse EIT present/following events.
    
    Args:
        stream: Stream reader
        eit_pid: Optional EIT PID (discovered if not provided)
        timeout: Maximum time to wait for EIT data (network streams)
        schedule_timeout: Time to wait for schedule data (for next fallback)
    
    Returns:
        Dict with 'present' and 'next' events
    """
    if eit_pid is None:
        pat = find_pat(stream)
        eit_pid = get_eit_pid(stream, pat)

    stream.seek(0)
    eit_sections = find_eit_packets(stream, eit_pid, timeout=timeout)
    
    present_event = None
    next_event = None
    schedule_events = []
    
    for section_data in eit_sections:
        section = parse_eit_section(section_data)
        if section is None:
            continue
        
        if section['current_next_indicator'] != 1:
            continue
        
        table_id = section['table_id']
        events = section.get('events', [])
        
        if table_id == EIT_TABLE_ID_PRESENT_FOLLOWING:
            for event in events:
                if event.get('running_status') == 4 and present_event is None:
                    present_event = event
                elif event.get('running_status') == 1 and next_event is None:
                    next_event = event
            
            schedule_events.extend(
                e for e in events
                if e.get('running_status') not in (1, 4)
            )
        
        elif (
            table_id >= EIT_TABLE_ID_SCHEDULE_START
            and table_id <= EIT_TABLE_ID_SCHEDULE_END
        ):
            schedule_events.extend(events)
        
        if present_event and next_event:
            break
    
    if next_event is None and schedule_events:
        schedule_events.sort(key=lambda e: e.get('start_time', ''))
        for evt in schedule_events:
            if evt.get('event_id') != present_event.get('event_id'):
                next_event = evt
                break
    
    metadata = {}
    for section_data in eit_sections:
        section = parse_eit_section(section_data)
        if section and section['table_id'] == EIT_TABLE_ID_PRESENT_FOLLOWING:
            metadata = {
                'network_id': section.get('original_network_id'),
                'transport_stream_id': section.get('transport_stream_id'),
                'service_id': section.get('service_id'),
            }
            break
    
    return {
        'present': present_event,
        'next': next_event,
        'metadata': metadata,
    }


def parse_eit_schedule(
    stream: StreamBase,
    eit_pid: int | None = None,
    max_events: int = 10,
    timeout: float = 5.0,
) -> list[dict]:
    """Parse EIT schedule events.
    
    Args:
        stream: Stream reader
        eit_pid: Optional EIT PID
        max_events: Maximum events to return (1-40)
        timeout: Maximum time to wait for EIT data (network streams)
    
    Returns:
        List of schedule events
    """
    max_events = max(1, min(40, max_events))
    
    if eit_pid is None:
        pat = find_pat(stream)
        eit_pid = get_eit_pid(stream, pat)

    stream.seek(0)
    eit_sections = find_eit_packets(
        stream, eit_pid, max_packets=5000, timeout=timeout,
    )
    
    events = []
    for section_data in eit_sections:
        section = parse_eit_section(section_data)
        if section is None:
            continue
        
        table_id = section['table_id']
        if (
            table_id < EIT_TABLE_ID_SCHEDULE_START
            or table_id > EIT_TABLE_ID_SCHEDULE_END
        ):
            continue
        
        if section['current_next_indicator'] != 1:
            continue
        
        for event in section.get('events', []):
            if len(events) >= max_events:
                return events
            events.append(event)
    
    return events
