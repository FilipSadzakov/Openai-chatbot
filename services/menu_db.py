import json
from typing import Any, List, Dict

def load_dishes(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
