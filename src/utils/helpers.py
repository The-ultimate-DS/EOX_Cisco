import os
import json
import datetime
from typing import Dict, List, Any, Optional

def save_json(data: Any, filename: str) -> None:
    """Save data to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(filename: str) -> Optional[Any]:
    """Load data from a JSON file."""
    if not os.path.exists(filename):
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def read_file(filename: str) -> str:
    """Read text from a file."""
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(content: str, filename: str) -> None:
    """Write text to a file."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

def parse_product_list(file_content: str) -> List[str]:
    """Parse a file with a list of product IDs, one per line."""
    lines = file_content.strip().split('\n')
    return [line.strip() for line in lines if line.strip()]