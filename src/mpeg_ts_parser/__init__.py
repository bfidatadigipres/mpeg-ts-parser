"""MPEG-TS Parser - Extract DVB EIT programme metadata from MPEG Transport Streams."""

import logging
from typing import Any

from mpeg_ts_parser.eit import parse_eit_present_following
from mpeg_ts_parser.stream import StreamBase, create_stream
from mpeg_ts_parser.utils import build_folder_path

logger = logging.getLogger(__name__)

__version__ = "0.1.0"
__all__ = [
    "get_programme_info",
    "connect",
    "build_folder_path",
    "Session",
]


class Session:
    """Persistent session for faster repeated EIT queries.
    
    Keeps stream connection open for subsequent calls.
    Use as context manager for automatic cleanup.
    
    Example:
        with mtp.connect("rtp://@:30001", timeout=2.0) as session:
            result = session.get_programme_info()
    """
    
    def __init__(self, source: str, timeout: float = 2.0):
        self.source = source
        self.timeout = timeout
        self._stream: StreamBase | None = None
    
    def __enter__(self) -> "Session":
        self._stream = create_stream(self.source, self.timeout)
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.close()
    
    def get_programme_info(
        self,
    ) -> dict:
        """Get present/next EIT events from the stream.
        
        Returns:
            Dict with present/next events and metadata
        """
        if self._stream is None:
            raise RuntimeError(
                "Session not opened. Use 'with' statement or call __enter__()."
            )
        
        try:
            eit_data = parse_eit_present_following(
                self._stream, timeout=self.timeout,
            )
            
            present = eit_data.get('present')
            next_evt = eit_data.get('next')
            metadata = eit_data.get('metadata', {})
            
            if present or next_evt:
                status = 'success'
            else:
                status = 'eit_unavailable'
            
            return {
                'status': status,
                'present': present,
                'next': next_evt,
                'metadata': metadata,
            }
        
        except Exception as e:
            logger.error("Failed to get programme info: %s", e)
            return {
                'status': 'error',
                'present': None,
                'next': None,
                'metadata': {},
                'error': str(e),
            }
    
    def close(self) -> None:
        """Close the stream."""
        if self._stream:
            self._stream.close()
            self._stream = None


def get_programme_info(
    source: str,
    timeout: float = 2.0,
) -> dict:
    """Get present/next EIT events from MPEG-TS source.
    
    Stateless call - opens stream, reads data, closes immediately.
    For repeated calls, use connect() for better performance.
    
    Args:
        source: RTP/UDP/HTTP URL or file path
        timeout: Socket timeout in seconds
    
    Returns:
        Dict with present/next events and metadata.
        Status is 'success', 'eit_unavailable', or 'error'.
    
    Example:
        result = mtp.get_programme_info("rtp://@:30001")
        if result['status'] == 'success':
            present = result['present']
            print(f"Event {present['event_id']}: {present['name']}")
    """
    stream = create_stream(source, timeout)
    
    try:
        eit_data = parse_eit_present_following(stream, timeout=timeout)
        
        present = eit_data.get('present')
        next_evt = eit_data.get('next')
        metadata = eit_data.get('metadata', {})
        
        if present or next_evt:
            status = 'success'
        else:
            status = 'eit_unavailable'
        
        return {
            'status': status,
            'present': present,
            'next': next_evt,
            'metadata': metadata,
        }
    
    except Exception as e:
        logger.error("Failed to get programme info: %s", e)
        return {
            'status': 'error',
            'present': None,
            'next': None,
            'metadata': {},
            'error': str(e),
        }
    
    finally:
        stream.close()


def connect(source: str, timeout: float = 2.0) -> Session:
    """Create persistent session for faster repeated EIT queries.
    
    Use as context manager for automatic cleanup.
    
    Args:
        source: RTP/UDP/HTTP URL or file path
        timeout: Socket timeout in seconds
    
    Returns:
        Session object
    
    Example:
        with mtp.connect("rtp://@:30001", timeout=2.0) as session:
            result = session.get_programme_info()
    """
    return Session(source, timeout)
