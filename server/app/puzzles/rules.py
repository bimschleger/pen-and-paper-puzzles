"""
Morning Puzzles - Game Rules & Guide Module
Loads and provides indexed access to canonical game rules, step-by-step
mechanics, move diagrams, and FAQs from server/data/game_rules.json.
"""

import os
from typing import Dict, Any, Optional, List
from .base import load_curated_dataset

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "game_rules.json")
_RULES_DATA: Optional[Dict[str, Any]] = None
_BY_KEY: Dict[str, Dict[str, Any]] = {}
_BY_ID: Dict[int, Dict[str, Any]] = {}


def load_game_rules() -> Dict[str, Any]:
    global _RULES_DATA, _BY_KEY, _BY_ID
    if _RULES_DATA is None:
        data = load_curated_dataset("game_rules.json")
        if data is None:
            raise FileNotFoundError(f"Canonical rules dataset not found at {DATA_PATH}")
        by_key: Dict[str, Dict[str, Any]] = {}
        by_id: Dict[int, Dict[str, Any]] = {}
        for game in data.get("games", []):
            by_key[game["key"].lower()] = game
            by_key[game["title"].lower()] = game
            by_id[game["id"]] = game
            # Legacy alias mappings
            if game["key"] == "search":
                by_key["wordsearch"] = game
            elif game["key"] == "stars":
                by_key["queens"] = game
        _BY_KEY = by_key
        _BY_ID = by_id
        _RULES_DATA = data
    return _RULES_DATA


def get_game_rule(identifier: Any) -> Optional[Dict[str, Any]]:
    """Retrieves canonical game rules by ID (int) or key/title (str)."""
    load_game_rules()
    if isinstance(identifier, int):
        return _BY_ID.get(identifier)
    s = str(identifier).strip().lower()
    return _BY_KEY.get(s)


def get_all_game_rules() -> List[Dict[str, Any]]:
    """Returns all canonical game rule specifications."""
    data = load_game_rules()
    return data.get("games", [])
