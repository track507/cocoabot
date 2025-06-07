import re
from datetime import datetime

def parse(input_str: str) -> str:
    input_str = input_str.strip().lower()
    
    input_str = re.sub(r'\bof\b', '', input_str, flags=re.IGNORECASE).strip()
    
    cleaned_input = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', input_str, flags=re.IGNORECASE)
    
    # Try MM-DD or MM/DD first
    match = re.match(r'^(\d{1,2})[-/](\d{1,2})$', cleaned_input)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        return f"{month:02d}-{day:02d}"

    # Now try Month Day
    try:
        parsed = datetime.strptime(cleaned_input, "%B %d")
        return f"{parsed.month:02d}-{parsed.day:02d}"
    except ValueError:
        pass

    # Try Day Month (reverse)
    try:
        parsed = datetime.strptime(cleaned_input, "%d %B")
        return f"{parsed.month:02d}-{parsed.day:02d}"
    except ValueError:
        pass
    
    return f"{month:02d}-{day:02d}"