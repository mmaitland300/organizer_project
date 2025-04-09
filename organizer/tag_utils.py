# tag_utils.py

import re

def parse_multi_dim_tags(tag_string: str) -> dict:
    """
    Parse an input string into a dictionary of tags.
    Tags with a colon are split into dimension and value;
    tokens without a colon are stored under the "general" dimension.
    Supports delimiters: comma and semicolon.
    
    Args:
        tag_string (str): Input string containing tags
        
    Returns:
        dict: Dictionary of tag dimensions and their values
        
    Raises:
        ValueError: If tag_string contains invalid format
    """
    if not isinstance(tag_string, str):
        raise ValueError("Tag string must be a string type")
        
    delimiters = [",", ";"]
    tokens = []
    
    try:
        for delimiter in delimiters:
            if delimiter in tag_string:
                tokens = [tok.strip() for tok in tag_string.split(delimiter) if tok.strip()]
                break
        if not tokens:
            tokens = [tag_string.strip()] if tag_string.strip() else []

        tag_dict = {}
        for token in tokens:
            if ":" in token:
                dimension, tag = token.split(":", 1)
                dimension = dimension.strip().lower()
                if not dimension:
                    raise ValueError(f"Empty dimension in token: {token}")
                tag = tag.strip().upper()
                if not tag:
                    raise ValueError(f"Empty tag value in token: {token}")
                tag_dict.setdefault(dimension, [])
                if tag not in tag_dict[dimension]:
                    tag_dict[dimension].append(tag)
            else:
                tag_dict.setdefault("general", [])
                token_upper = token.strip().upper()
                if token_upper and token_upper not in tag_dict["general"]:
                    tag_dict["general"].append(token_upper)
        return tag_dict
        
    except Exception as e:
        raise ValueError(f"Error parsing tag string: {str(e)}")

def format_multi_dim_tags(tag_dict: dict) -> str:
    """
    Format a multi-dimensional tag dictionary into a display-friendly string.
    For example, {"genre": ["ROCK"], "mood": ["HAPPY"]} becomes "Genre: ROCK; Mood: HAPPY".
    """
    parts = []
    for dimension, tags in tag_dict.items():
        dim_display = dimension.capitalize()
        tags_display = ", ".join(tags)
        parts.append(f"{dim_display}: {tags_display}")
    return "; ".join(parts)

def validate_tag_dimension(dimension: str) -> bool:
    """
    Validate a tag dimension name.
    
    Args:
        dimension (str): The dimension name to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not dimension:
        return False
    # Add any specific validation rules
    # e.g., no special characters except underscore
    return bool(re.match(r'^[a-zA-Z0-9_]+$', dimension))

def normalize_tag(tag: str) -> str:
    """
    Normalize a tag value by removing invalid characters and converting to uppercase.
    
    Args:
        tag (str): The tag to normalize
        
    Returns:
        str: Normalized tag value
    """
    # Remove special characters except hyphen and underscore
    normalized = re.sub(r'[^\w\s-]', '', tag)
    # Convert to uppercase and strip whitespace
    return normalized.strip().upper()
