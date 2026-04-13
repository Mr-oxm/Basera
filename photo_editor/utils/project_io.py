"""Basera project snapshot I/O.

A .basera file stores a full in-memory snapshot of the current document
(state + history) using a compressed pickle payload.
"""

from __future__ import annotations

import copy
import gzip
import os
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.document import Document
from ..core.history import HistoryState

if TYPE_CHECKING:
    pass


_BASERA_MAGIC = "BASERA_PROJECT"
_BASERA_VERSION = 1


def _clone_history_state(state: HistoryState) -> dict:
    """Clone history state payload so serialization does not share references."""
    return {
        "name": state.name,
        "metadata": copy.deepcopy(state.metadata),
        "layer_data": {k: v.copy() for k, v in state.layer_data.items()},
    }


def build_basera_payload(document: Document) -> dict:
    """Build a complete project snapshot payload for .basera export."""
    current_state = document._build_history_state("__ProjectSnapshot__")

    return {
        "magic": _BASERA_MAGIC,
        "version": _BASERA_VERSION,
        "document": {
            "name": document.name,
            "width": document.width,
            "height": document.height,
            "dpi": document.dpi,
            "file_path": document.file_path,
            "dirty": document.dirty,
        },
        "current_state": _clone_history_state(current_state),
        "history": {
            "states": [_clone_history_state(s) for s in document.history.states],
            "current_index": document.history.current_index,
        },
    }


def save_basera_project(document: Document, path: str | Path) -> None:
    """Write a complete project snapshot to a .basera file.

    Uses an atomic temp-file + replace strategy so interrupted writes
    never leave a partially written project at the target path.
    """
    target = Path(path)
    payload = build_basera_payload(document)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")

    try:
        with gzip.open(tmp, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)

        # Validate stream before replacing destination.
        _ = load_basera_payload(tmp)
        os.replace(tmp, target)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def load_basera_payload(path: str | Path) -> dict:
    """Load raw .basera payload for validation/debugging/tests."""
    source = Path(path)
    try:
        with gzip.open(source, "rb") as fh:
            payload = pickle.load(fh)
    except (OSError, EOFError, pickle.UnpicklingError) as exc:
        raise ValueError(
            "Project file is incomplete or corrupted. "
            "Please save again and wait for the save confirmation before reopening."
        ) from exc
    if not isinstance(payload, dict) or payload.get("magic") != _BASERA_MAGIC:
        raise ValueError("Invalid .basera file")
    return payload


def _state_from_payload(data: dict) -> HistoryState:
    """Convert serialized state dict to a HistoryState instance."""
    return HistoryState(
        name=data.get("name", "Unnamed"),
        metadata=copy.deepcopy(data.get("metadata", {})),
        layer_data={k: v.copy() for k, v in data.get("layer_data", {}).items()},
    )


def load_basera_project(path: str | Path) -> Document:
    """Load a .basera project file and rebuild a full Document object."""
    payload = load_basera_payload(path)

    meta = payload.get("document", {})
    width = int(meta.get("width", 1))
    height = int(meta.get("height", 1))
    name = str(meta.get("name", "Untitled"))

    document = Document(width, height, name=name)
    document.dpi = int(meta.get("dpi", 72))
    document.file_path = str(path)

    current_state_data = payload.get("current_state")
    if not isinstance(current_state_data, dict):
        raise ValueError("Invalid .basera file: missing current_state")
    current_state = _state_from_payload(current_state_data)
    document._restore(current_state)

    # Restore history timeline.
    hist = payload.get("history", {})
    states_data = hist.get("states", [])
    history_states: list[HistoryState] = []
    for item in states_data:
        if isinstance(item, dict):
            history_states.append(_state_from_payload(item))
    document.history._states = history_states

    if history_states:
        saved_index = int(hist.get("current_index", len(history_states)))
        # Saved index may point to the synthetic "live" row (len(states)).
        if saved_index >= len(history_states):
            document.history._index = len(history_states) - 1
        elif saved_index < 0:
            document.history._index = 0
        else:
            document.history._index = saved_index
    else:
        document.history._index = -1

    if bool(meta.get("dirty", False)):
        document.mark_dirty()
    else:
        document.mark_clean()

    return document
