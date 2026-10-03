"""Small, non-secret preferences; the config and its guard are never relocated."""
import json
from pathlib import Path
from thsr_ticket.run_records import atomic_json


class Preferences:
    def __init__(self, directory):
        self.path = Path(directory) / 'preferences.json'

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def remember(self, config_path):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, {'last_config': str(Path(config_path).resolve())})
