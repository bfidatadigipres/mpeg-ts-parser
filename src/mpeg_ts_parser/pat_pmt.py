"""PAT and PMT parsers for MPEG-TS, with EIT PID discovery."""

import logging

from mpeg_ts_parser.stream import StreamBase, parse_ts_header

logger = logging.getLogger(__name__)

TS_PACKET_SIZE = 188
PAT_PID = 0x0000
PAT_TABLE_ID = 0x00
PMT_TABLE_ID = 0x02
EIT_PID_STANDARD = 0x0012
EIT_STREAM_TYPE = 0x06
EIT_LINKAGE_DESCRIPTOR = 0x4A
SHORT_EVENT_DESCRIPTOR = 0x4D


def parse_pat_payload(payload: bytes) -> dict | None:
    """Parse PAT section from payload.
    
    Args:
        payload: PAT payload bytes (after pointer field if present)
    
    Returns:
        PAT dict with programme mappings, or None
    """
    if len(payload) < 8:
        return None
    
    table_id = payload[0]
    if table_id != PAT_TABLE_ID:
        return None
    
    section_length = ((payload[1] & 0x0F) << 8) | payload[2]
    
    if len(payload) < 3 + section_length:
        logger.warning("PAT section truncated")
        return None
    
    transport_stream_id = (payload[3] << 8) | payload[4]
    version_number = (payload[5] >> 1) & 0x1F
    current_next_indicator = payload[5] & 0x01
    section_number = payload[6]
    last_section_number = payload[7]
    
    programmes = {}
    offset = 8
    section_end = 3 + section_length - 4
    
    while offset + 4 <= section_end:
        programme_number = (payload[offset] << 8) | payload[offset + 1]
        pid = ((payload[offset + 2] & 0x1F) << 8) | payload[offset + 3]
        
        programmes[programme_number] = pid
        offset += 4
    
    return {
        'table_id': table_id,
        'version_number': version_number,
        'current_next_indicator': current_next_indicator,
        'section_number': section_number,
        'last_section_number': last_section_number,
        'transport_stream_id': transport_stream_id,
        'programmes': programmes,
    }


def parse_pmt_payload(payload: bytes) -> dict | None:
    """Parse PMT section from payload.
    
    Args:
        payload: PMT payload bytes
    
    Returns:
        PMT dict with elementary streams, or None
    """
    if len(payload) < 12:
        return None
    
    table_id = payload[0]
    if table_id != PMT_TABLE_ID:
        return None
    
    section_length = ((payload[1] & 0x0F) << 8) | payload[2]
    
    if len(payload) < 3 + section_length:
        logger.warning("PMT section truncated")
        return None
    
    programme_number = (payload[3] << 8) | payload[4]
    version_number = (payload[5] >> 1) & 0x1F
    current_next_indicator = payload[5] & 0x01
    section_number = payload[6]
    last_section_number = payload[7]
    
    pcr_pid = ((payload[8] & 0x1F) << 8) | payload[9]
    program_info_length = ((payload[10] & 0x0F) << 8) | payload[11]
    
    elementary_streams = []
    offset = 12 + program_info_length
    section_end = 3 + section_length - 4
    
    while offset + 5 <= section_end:
        stream_type = payload[offset]
        elementary_pid = ((payload[offset + 1] & 0x1F) << 8) | payload[offset + 2]
        es_info_length = ((payload[offset + 3] & 0x0F) << 8) | payload[offset + 4]
        
        descriptors = []
        if es_info_length > 0 and offset + 5 + es_info_length <= section_end:
            desc_offset = offset + 5
            desc_end = offset + 5 + es_info_length
            while desc_offset + 2 <= desc_end:
                desc_tag = payload[desc_offset]
                desc_length = payload[desc_offset + 1]
                if desc_offset + 2 + desc_length <= desc_end:
                    descriptors.append({
                        'tag': desc_tag,
                        'length': desc_length,
                        'data': payload[desc_offset + 2:desc_offset + 2 + desc_length],
                    })
                desc_offset += 2 + desc_length
        
        elementary_streams.append({
            'stream_type': stream_type,
            'elementary_pid': elementary_pid,
            'es_info_length': es_info_length,
            'descriptors': descriptors,
        })
        
        offset += 5 + es_info_length
    
    return {
        'table_id': table_id,
        'version_number': version_number,
        'current_next_indicator': current_next_indicator,
        'section_number': section_number,
        'last_section_number': last_section_number,
        'programme_number': programme_number,
        'pcr_pid': pcr_pid,
        'elementary_streams': elementary_streams,
    }


def discover_eit_pid_from_pmt(pmt_data: dict) -> int | None:
    """Discover EIT PID from PMT elementary stream descriptors.
    
    Looks for stream_type 0x06 with linkage descriptor (tag 0x4A).
    
    Args:
        pmt_data: Parsed PMT dict
    
    Returns:
        EIT PID, or None if not found
    """
    for stream in pmt_data.get('elementary_streams', []):
        if stream['stream_type'] == EIT_STREAM_TYPE:
            for desc in stream.get('descriptors', []):
                if desc['tag'] == EIT_LINKAGE_DESCRIPTOR:
                    logger.info(
                        "Discovered EIT PID %d from PMT descriptors",
                        stream['elementary_pid'],
                    )
                    return stream['elementary_pid']
    
    return None


def find_pat(stream: StreamBase, max_packets: int = 200) -> dict | None:
    """Find and parse PAT from stream.
    
    Args:
        stream: Stream reader
        max_packets: Maximum packets to scan
    
    Returns:
        Parsed PAT dict, or None
    """
    packets = stream.read_packets(max_packets)
    
    for packet in packets:
        header = parse_ts_header(packet)
        if header is None:
            continue
        
        if header['pid'] == PAT_PID:
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
            
            if header['payload_unit_start_indicator'] and len(payload) > 0:
                pointer_field = payload[0]
                payload = payload[1 + pointer_field:]
            
            pat = parse_pat_payload(payload)
            if pat:
                logger.info(
                    "Found PAT: transport_stream_id=%d, version=%d, programmes=%d",
                    pat['transport_stream_id'],
                    pat['version_number'],
                    len(pat['programmes']),
                )
                return pat
    
    logger.warning("PAT not found in %d packets", max_packets)
    return None


def find_pmt(stream: StreamBase, pmt_pid: int, max_packets: int = 200) -> dict | None:
    """Find and parse PMT from stream.
    
    Args:
        stream: Stream reader
        pmt_pid: PMT PID from PAT
        max_packets: Maximum packets to scan
    
    Returns:
        Parsed PMT dict, or None
    """
    packets = stream.read_packets(max_packets)
    
    for packet in packets:
        header = parse_ts_header(packet)
        if header is None:
            continue
        
        if header['pid'] == pmt_pid:
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
            
            if header['payload_unit_start_indicator'] and len(payload) > 0:
                pointer_field = payload[0]
                payload = payload[1 + pointer_field:]
            
            pmt = parse_pmt_payload(payload)
            if pmt:
                logger.info(
                    "Found PMT: programme_number=%d, version=%d, streams=%d",
                    pmt['programme_number'],
                    pmt['version_number'],
                    len(pmt['elementary_streams']),
                )
                return pmt
    
    logger.warning("PMT not found for PID %d in %d packets", pmt_pid, max_packets)
    return None


def get_eit_pid(stream: StreamBase, pat: dict | None = None) -> int:
    """Get EIT PID, trying standard first then PMT discovery.
    
    Args:
        stream: Stream reader
        pat: Optional pre-parsed PAT
    
    Returns:
        EIT PID
    """
    logger.info("Trying standard EIT PID %d", EIT_PID_STANDARD)
    
    if pat is None:
        pat = find_pat(stream)
    
    if pat is None:
        logger.warning("PAT not found, using standard EIT PID")
        return EIT_PID_STANDARD
    
    programmes = pat.get('programmes', {})
    non_zero_programmes = {k: v for k, v in programmes.items() if k != 0}
    
    if not non_zero_programmes:
        logger.warning("No programmes in PAT, using standard EIT PID")
        return EIT_PID_STANDARD
    
    first_pmt_pid = next(iter(non_zero_programmes.values()))
    pmt = find_pmt(stream, first_pmt_pid)
    
    if pmt:
        eit_pid = discover_eit_pid_from_pmt(pmt)
        if eit_pid is not None:
            return eit_pid
    
    logger.info("EIT not found in PMT, using standard PID %d", EIT_PID_STANDARD)
    return EIT_PID_STANDARD
