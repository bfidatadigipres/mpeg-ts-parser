# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-08-26

### Added

- MPEG-TS packet parsing with automatic RTP header detection and stripping (RFC 3550)
- PAT (Program Association Table) parsing for programme-to-PMT mapping
- PMT (Program Map Table) parsing with EIT PID discovery from descriptors
- EIT (Event Information Table) parsing for present/following events
- Multi-packet EIT section reassembly for sections spanning multiple TS packets
- `running_status`-based event assignment (4=present, 1=next) for UK broadcaster compatibility
- DVB control character (`\x86`/`\x87`) stripping from event names
- Folder path builder for archive organisation (`HH-MM-SS_eventId_HH-MM-SS`)
- `SO_REUSEADDR` socket option for simultaneous VLC recording + parser monitoring
- File stream support with `seek()` for post-recording analysis
- Persistent session support via context manager for faster repeated queries
- Full type hints throughout
- Comprehensive test suite (41 tests)
- GitHub Actions CI workflow testing Python 3.11, 3.12, and 3.13

[0.1.0]: https://github.com/bfidatadigipres/mpeg-ts-parser/releases/tag/v0.1.0
