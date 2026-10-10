"""Tiny local JSON store for things that should survive a restart: owner-entered events, alert and waste
decisions, order status records and preferences. One file, one machine, one user (a prototype; a real deployment
would use a database). Path: $LARIS_STATE or ./state/laris_state.json.
"""
import json
import os
from datetime import datetime
from pathlib import Path

DEFAULT = Path(__file__).parent / "state" / "laris_state.json"


def _path():
    return Path(os.environ.get("LARIS_STATE", DEFAULT))


def load():
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(key, default=None):
    return load().get(key, default)


def put(key, value):
    data = load()
    data[key] = value
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def update(key, sub, value):
    """Set data[key][sub] = value (a dict entry) and return the whole dict."""
    d = get(key, {})
    d[sub] = value
    put(key, d)
    return d


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")
