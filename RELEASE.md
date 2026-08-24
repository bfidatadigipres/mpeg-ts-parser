# Release Guide

## Build Package

```bash
cd ~/git/mpeg-ts-parser
source .venv/bin/activate
pip install --upgrade build twine
python -m build
```

This creates two files in `dist/`:
- `mpeg_ts_parser-0.1.0.tar.gz` (source distribution)
- `mpeg_ts_parser-0.1.0-py3-none-any.whl` (wheel)

## Test on TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

Verify at: https://test.pypi.org/project/mpeg-ts-parser/

Test install:
```bash
pip install --index-url https://test.pypi.org/simple/ --no-deps mpeg-ts-parser
```

## Release to Production PyPI

```bash
python -m twine upload dist/*
```

Verify at: https://pypi.org/project/mpeg-ts-parser/

## Authentication

Create an API token at:
- TestPyPI: https://test.pypi.org/manage/account/#api-tokens
- PyPI: https://pypi.org/manage/account/#api-tokens

Use username `__token__` and the full token (including `pypi-` prefix) as password.

Or configure `~/.pypirc`:
```ini
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE

[testpypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE
```

## Version Bump

Edit `version = "0.1.0"` in `pyproject.toml` before each release.

Follow semantic versioning: `MAJOR.MINOR.PATCH`
- `0.1.0` → `0.1.1` (bug fix)
- `0.1.0` → `0.2.0` (new feature)
- `0.1.0` → `1.0.0` (stable release)
