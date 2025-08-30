import json

def save_json_pretty(data, filename="output.json"):
    """
    Save JSON data in a human-readable, structured format.
    
    Args:
        data (dict | list | str): JSON object, list, or raw JSON string
        filename (str): File to save the formatted JSON
    """
    # If data is a raw JSON string, parse it first
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON string: {e}")
            return

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)  # indent=4 → pretty formatting

    print(f"JSON saved in structured format to {filename}")


# Example usage:
#load a json file
with open("C:\\Users\\Dharani\\Downloads\\NSE\\NSE.json", "r", encoding="utf-8") as f:
    raw_json = json.load(f)

save_json_pretty(raw_json, "formatted.json")