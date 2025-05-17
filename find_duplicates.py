import json

def find_duplicate_objects(file_path):
    """
    Iterates through a JSON file containing a list of objects and returns a list of duplicate objects.
    An object is considered a duplicate if all its key-value pairs match another object in the list.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return "Error: File not found."
    except json.JSONDecodeError:
        return "Error: Invalid JSON format."

    if not isinstance(data, list):
        return "Error: JSON content must be a list of objects."

    seen_objects = []
    duplicates = []

    for i, obj1 in enumerate(data):
        is_duplicate_found = False
        # Check if this object (obj1) is a duplicate of any object already processed
        for seen_obj in seen_objects:
            if obj1 == seen_obj:
                # Check if this specific duplicate instance is already in the duplicates list
                # This avoids adding the same object multiple times if it appears more than twice
                is_already_in_duplicates = False
                for dup in duplicates:
                    if obj1 == dup:
                        is_already_in_duplicates = True
                        break
                if not is_already_in_duplicates:
                    duplicates.append(obj1)
                is_duplicate_found = True
                break # Found a match in seen_objects, no need to check further for obj1
        
        if not is_duplicate_found:
            # If obj1 is not a duplicate of already seen objects, add it to seen_objects
            seen_objects.append(obj1)
        
    return duplicates

if __name__ == "__main__":
    file_to_analyze = "data-16-05-25.json"
    duplicate_items = find_duplicate_objects(file_to_analyze)

    if isinstance(duplicate_items, str): # Error message was returned
        print(duplicate_items)
    elif not duplicate_items:
        print(f"No duplicate objects found in {file_to_analyze}.")
    else:
        print(f"Duplicate objects found in {file_to_analyze}:")
        # Pretty print the JSON output
        print(json.dumps(duplicate_items, indent=2, ensure_ascii=False))
