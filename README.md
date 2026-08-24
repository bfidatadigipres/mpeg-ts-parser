# mpeg-ts-parser

Parse MPEG Transport Streams to extract DVB EIT programme metadata.

## Features

- Extract present/next programme events from DVB EIT tables
- Support for RTP, UDP, HTTP, and file-based MPEG-TS sources
- Automatic RTP header detection and stripping
- EIT PID discovery from PMT descriptors
- Optional schedule event extraction
- Pure Python, no external dependencies
- Full type hints

## Installation

```bash
pip install mpeg-ts-parser
```

## Quick Start

### Stateless Call

```python
import mpeg_ts_parser as mtp

result = mtp.get_programme_info("rtp://@:30001", timeout=2.0)

if result['status'] == 'success':
    present = result['present']
    print(f"Event {present['event_id']}: {present['name']}")
    print(f"Start: {present['start_time']}, Duration: {present['duration']}")
elif result['status'] == 'eit_unavailable':
    print("EIT data not available")
```

### Persistent Session (Faster Repeated Calls)

```python
with mtp.connect("rtp://@:30001", timeout=2.0) as session:
    result = session.get_programme_info()
    # Subsequent calls are faster
    result2 = session.get_programme_info()
```

### Include Schedule Events

```python
result = mtp.get_programme_info(
    "rtp://@:30001",
    include_schedule=True,
    max_schedule_events=20,
)

for event in result['schedule']:
    print(f"Event {event['event_id']}: {event['name']}")
```

### Build Folder Path

```python
event = result['present']
folder = mtp.build_folder_path(event, format="string")
# Returns: "09-00-00_1425_00-30-00"

folder_list = mtp.build_folder_path(event, format="list")
# Returns: ['09', '00', '00', '1425', '00', '30', '00']
```

## Supported Sources

- `rtp://@:30001` - RTP stream (auto-detects and strips RTP headers)
- `udp://@:30001` - Raw UDP stream
- `http://server:8080/stream.ts` - HTTP stream
- `/path/to/file.ts` - Local file (with optional RTP headers)

## Return Structure

```python
{
    'status': 'success' | 'eit_unavailable' | 'error',
    'present': {
        'event_id': 1425,
        'start_time': '09-00-00',
        'duration': '00-30-00',
        'name': 'Programme Name',
    } | None,
    'next': { ... } | None,
    'schedule': [...],  # Optional
    'metadata': {
        'network_id': 1234,
        'transport_stream_id': 5678,
        'service_id': 9012,
    }
}
```

## API Reference

### `get_programme_info(source, timeout=2.0, include_schedule=False, max_schedule_events=10)`

Stateless call to get present/next EIT events.

### `connect(source, timeout=2.0)`

Create persistent session for faster repeated calls. Use as context manager.

### `build_folder_path(event, format="string")`

Build folder path from event data. Format: `"string"` or `"list"`.

## Development

```bash
git clone https://github.com/whitej/mpeg-ts-parser.git
cd mpeg-ts-parser
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
