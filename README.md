# mpeg-ts-parser

Extract DVB EIT programme metadata from standard 188-byte MPEG Transport Streams.

## Project Context

This package was developed as part of **[STORA](https://github.com/bfidatadigipres/STORA)** (System for Television Off-air Recording and Archiving), the open-source recording system used by the **[BFI National Television Archive](https://www.bfi.org.uk/archive-collections)**.

STORA records 17 UK television channels 24 hours a day, 7 days a week, preserving broadcast television under the provision of the Broadcasting Act 1990. This parser will replace the `libdvbtee` dependency, enabling EIT extraction directly from RTP streams and eliminating the need for separate UDP monitoring streams.

## What This Package Does

Parses MPEG-TS files and live streams to extract **DVB Event Information Table (EIT)** data:

- **Event ID** - Unique programme identifier
- **Start time** - Programme start (HH-MM-SS)
- **Duration** - Programme length (HH-MM-SS)
- **Event name** - Programme title (DVB control characters stripped)
- **Running status** - Currently airing vs starts soon
- **Free/CA mode** - Free-to-air vs scrambled

## Primary Use Cases

### 1. Monitoring Live Satellite/Cable Streams

```python
import mpeg_ts_parser as mtp

result = mtp.get_programme_info("rtp://@:30001", timeout=2.0)
if result['status'] == 'success':
    print(f"Now: {result['present']['name']} (ID: {result['present']['event_id']})")
    print(f"Next: {result['next']['name']} (ID: {result['next']['event_id']})")
```

Perfect for:
- Recording automation (detect programme changes to split recordings)
- EPG data collection from live DVB-S/S2/T/T2 streams
- Channel monitoring systems

### 2. Analysing Recorded TS Files

```python
result = mtp.get_programme_info("/path/to/recording.ts")
folder = mtp.build_folder_path(result['present'])
# Returns: "09-00-00_1425_00-30-00"
```

Perfect for:
- Post-recording metadata extraction
- File organisation and naming
- Archive cataloguing

### 3. Persistent Session for Repeated Queries

```python
with mtp.connect("rtp://@:30001", timeout=2.0) as session:
    while recording:
        result = session.get_programme_info()
        # Check for programme changes...
```

Perfect for:
- Long-running monitoring daemons
- 24/7 channel recording systems
- Real-time programme change detection

## Supported Sources

| Source Type | Example | Notes |
|-------------|---------|-------|
| RTP/UDP multicast | `rtp://@:30001` | Auto-detects/strips RTP headers, `SO_REUSEADDR` enabled |
| Raw UDP | `udp://@:30001` | Same as RTP, without RTP header detection |
| Local TS file | `/path/to/recording.ts` | Supports `.ts`, `.m2t` extensions |
| HTTP stream | `http://server:8080/stream.ts` | Basic HTTP MPEG-TS |

## Not Supported

This package is specifically designed for **standard 188-byte MPEG-TS with DVB EIT data**. The following are **not supported**:

| Format | Reason |
|--------|--------|
| Blu-ray `.m2ts` / AVCHD | Uses 192-byte packets with timestamp prefix |
| HLS / `.m3u8` playlists | Requires playlist parsing, segment downloading |
| DASH / `.mpd` manifests | Requires manifest parsing, segment handling |
| SMPTE ST 2022-2 | Different protocol with FEC and timing recovery |
| Proprietary camcorder formats (`.tod`, etc.) | Undocumented, non-standard |
| Video/audio stream parsing | Only parses PSI/SI tables (PAT, PMT, EIT) |

## Quick Start

### Installation

Requires **Python 3.11+**.

```bash
pip install mpeg-ts-parser
```

### Basic Usage

```python
import mpeg_ts_parser as mtp

result = mtp.get_programme_info("rtp://@:30001", timeout=2.0)

if result['status'] == 'success':
    present = result['present']
    print(f"Event {present['event_id']}: {present['name']}")
    print(f"Start: {present['start_time']}, Duration: {present['duration']}")
elif result['status'] == 'eit_unavailable':
    print("EIT data not available in this stream")
```

### Build Folder Path

```python
event = result['present']
folder = mtp.build_folder_path(event, format="string")
# Returns: "09-00-00_1425_00-30-00"

folder_list = mtp.build_folder_path(event, format="list")
# Returns: ['09-00-00', '1425', '00-30-00']
```

## Understanding Present/Next Events

UK satellite broadcasters typically send present and following events in **separate EIT sections**, rotating in the stream. The parser uses the `running_status` field to assign events:

| running_status | Meaning | Assigned to |
|----------------|---------|-------------|
| 4 | Currently running | `present` |
| 1 | Starts soon | `next` |

### How It Works

1. The parser reads EIT sections from the stream
2. Events with `running_status=4` populate `present`
3. Events with `running_status=1` populate `next`

### Event Fields

Each event dict contains:

```python
{
    'event_id': 1425,           # Unique programme identifier
    'start_time': '09-00-00',   # UTC Start time (HH-MM-SS)
    'duration': '00-30-00',     # Duration (HH-MM-SS)
    'name': 'Programme Name',   # Event name (control chars stripped)
    'running_status': 4,        # 1=starts soon, 4=current
    'free_ca_mode': 0,          # 0=free-to-air, 1=scrambled
}
```

### Status Values

| status | Meaning |
|--------|---------|
| `success` | At least one event found |
| `eit_unavailable` | No EIT data in stream |
| `error` | Parsing error occurred |

## Return Structure

```python
{
    'status': 'success' | 'eit_unavailable' | 'error',
    'present': {
        'event_id': 1425,
        'start_time': '09-00-00',
        'duration': '00-30-00',
        'name': 'Programme Name',
        'running_status': 4,
        'free_ca_mode': 0,
    } | None,
    'next': { ... } | None,
    'metadata': {
        'network_id': 1234,
        'transport_stream_id': 5678,
        'service_id': 9012,
    }
}
```

## API Reference

### `get_programme_info(source, timeout=2.0)`

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

## How It Works: MPEG-TS Packet Structure

### The 188-Byte Packet

Every MPEG Transport Stream is built from fixed-size **188-byte packets**. This size was chosen for ATM (Asynchronous Transfer Mode) network compatibility — 188 bytes fits neatly into ATM's 53-byte cell structure (4 cells × 47 bytes payload = 188).

Each packet has a 4-byte header followed by 184 bytes of payload:

```
╔══════════════════════════════════════════════════════════╗
║ 4-byte Header               ║ 184-byte Payload           ║
╠═════════════════════════════╬════════════════════════════╣
║ Sync byte (0x47)            ║ PSI/SI table data          ║
║ Transport error indicator   ║ or video/audio elementary  ║
║ Payload unit start indicator║ stream data                ║
║ Transport priority          ║                            ║
║ PID (13 bits)               ║                            ║
║ Scrambling control          ║                            ║
║ Adaptation field control    ║                            ║
║ Continuity counter          ║                            ║
╚═════════════════════════════╩════════════════════════════╝
```

The **sync byte (`0x47`)** marks the start of every packet. The **PID (Packet Identifier)** tells you what type of data the packet carries.

### Key PIDs

| PID | Name | Purpose |
|-----|------|---------|
| `0x0000` | PAT | Program Association Table — lists all programmes and their PMT PIDs |
| `0x0001` | CAT | Conditional Access Table |
| `0x0010` | NIT | Network Information Table |
| `0x0011` | SDT | Service Description Table — channel names |
| `0x0012` | EIT | Event Information Table — programme metadata |
| `0x1FFF` | Null | Padding packets |

Other PIDs are assigned dynamically per programme (video, audio, subtitles, etc.).

### How This Parser Extracts EIT Data

The parser follows a three-step process:

**Step 1: Find the PAT (PID `0x0000`)**

The PAT is the entry point to any MPEG-TS stream. It maps programme numbers to their PMT PIDs:

```
PAT: Programme 1 → PMT PID 0x0105
     Programme 2 → PMT PID 0x0200
     ...
```

The parser scans packets looking for PID `0x0000`, parses the PAT section, and extracts the PMT PID for the target programme.

**Step 2: Find the PMT (PID from PAT)**

The PMT describes the elementary streams (video, audio, subtitles) that make up a programme. Crucially, it may contain descriptors that reveal the EIT PID if it differs from the standard `0x0012`.

**Step 3: Find EIT Sections (PID `0x0012` or discovered)**

EIT sections contain the actual programme metadata. Each section has:
- `table_id`: `0x4E` (present/following) or `0x4F-0x5F` (schedule)
- `section_length`: total size of the section (may span multiple packets)
- Events with `event_id`, `start_time`, `duration`, `name`, `running_status`

### Why Section Reassembly Matters

EIT sections are often **larger than a single packet's 184-byte payload**. A typical present/following section might be 500+ bytes, requiring 3-4 packets to transmit.

The parser handles this by:
1. Detecting the `payload_unit_start_indicator` flag — marks the first packet of a new section
2. Reading the `section_length` field from the section header
3. Accumulating payload data across continuation packets until the full section is assembled
4. Only then parsing the complete section

For **file-based streams**, the parser uses `seek(0)` to reset to the start of the file before searching for EIT data, ensuring it finds sections regardless of where they appear in the file.

For **live RTP/UDP streams**, the parser uses `read_until_eit()` which continuously reads packets until complete EIT sections are assembled or the timeout is reached. The `SO_REUSEADDR` socket option allows multiple processes (e.g., VLC viewing + parser monitoring) to bind to the same UDP port simultaneously.

### RTP Header Stripping

When MPEG-TS is carried over RTP (RFC 3550), each packet has an additional RTP header prepended. The parser auto-detects this using the heuristic from RFC 3550:
- First byte `0x80` = RTP version 2
- Second byte payload type `33` = MPEG-TS payload

The header size is calculated as `12 + (csrc_count × 4)` bytes and stripped before TS packet parsing begins.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes.

## License

MIT
