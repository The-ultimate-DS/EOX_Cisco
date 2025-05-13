from crewai import tools
from src.utils.helpers import read_file, write_file, save_json, load_json

@tools.tool
def read_text_file(filename: str) -> str:
    """Read text from a file."""
    return read_file(filename)

@tools.tool
def write_text_file(content: str, filename: str) -> str:
    """Write text to a file."""
    write_file(content, filename)
    return f"Successfully wrote to {filename}"

@tools.tool
def save_json_file(data: dict, filename: str) -> str:
    """Save data to a JSON file."""
    save_json(data, filename)
    return f"Successfully saved JSON to {filename}"

@tools.tool
def load_json_file(filename: str) -> dict:
    """Load data from a JSON file."""
    data = load_json(filename)
    if data is None:
        return f"File {filename} not found or not valid JSON"
    return data