"""Utility functions for MPEG-TS parsing: time conversion, folder path building."""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MJD_EPOCH = datetime(1858, 11, 17)


def bcd_to_int(bcd_byte: int) -> int:
    """Convert a BCD-encoded byte to integer."""
    return ((bcd_byte >> 4) & 0x0F) * 10 + (bcd_byte & 0x0F)


def bcd_to_time(bcd_bytes: bytes) -> str:
    """Convert 3 BCD bytes (HH MM SS) to 'HH-MM-SS' string.
    
    Args:
        bcd_bytes: 3 bytes representing hours, minutes, seconds in BCD
    
    Returns:
        Formatted time string 'HH-MM-SS'
    """
    if len(bcd_bytes) != 3:
        logger.warning("Invalid BCD time bytes length: %d", len(bcd_bytes))
        return "00-00-00"
    
    hours = bcd_to_int(bcd_bytes[0])
    minutes = bcd_to_int(bcd_bytes[1])
    seconds = bcd_to_int(bcd_bytes[2])
    
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}"


def mjd_to_datetime(mjd_bytes: bytes) -> datetime:
    """Convert 2-byte MJD date to datetime.
    
    MJD (Modified Julian Date) encoding per ETSI EN 300 468.
    
    Args:
        mjd_bytes: 2 bytes representing MJD date
    
    Returns:
        datetime object
    """
    if len(mjd_bytes) != 2:
        logger.warning("Invalid MJD bytes length: %d", len(mjd_bytes))
        return datetime.now()
    
    mjd = (mjd_bytes[0] << 8) | mjd_bytes[1]
    return MJD_EPOCH + timedelta(days=mjd)


def parse_short_event_descriptor(data: bytes) -> str | None:
    """Parse ETSI EN 300 468 short_event_descriptor (tag 0x4D).
    
    Args:
        data: Descriptor payload (after tag and length bytes)
    
    Returns:
        Event name string, or None if parsing fails
    """
    if len(data) < 4:
        return None
    
    try:
        event_name_length = data[3]
        
        if len(data) < 4 + event_name_length:
            logger.warning("Short event descriptor truncated")
            return None
        
        event_name = data[4:4 + event_name_length].decode(
            'iso-8859-1', errors='replace'
        )
        return event_name.strip()
    except Exception as e:
        logger.warning("Failed to parse short event descriptor: %s", e)
        return None


def build_folder_path(event: dict, format: str = "string") -> str | list:
    """Build folder path from event data.
    
    Args:
        event: Event dict with 'start_time', 'event_id', 'duration'
        format: 'string' returns "HH-MM-SS_eventId_HH-MM-SS",
                'list' returns [HH, MM, SS, eventId, HH, MM, SS]
    
    Returns:
        Formatted folder path
    """
    start_time = event.get('start_time', '00-00-00')
    event_id = event.get('event_id', 0)
    duration = event.get('duration', '00-00-00')
    
    if format == "list":
        start_parts = start_time.split('-')
        duration_parts = duration.split('-')
        return [*start_parts, str(event_id), *duration_parts]
    
    return f"{start_time}_{event_id}_{duration}"
