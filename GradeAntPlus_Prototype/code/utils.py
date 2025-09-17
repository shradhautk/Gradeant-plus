import json
import logging
import os
from pathlib import Path

# ==============================================================================
# SECTION 1: LOGGER CONFIGURATION
# ==============================================================================

# Ensure the logs directory exists
LOG_DIR = Path(__file__).parent.parent / "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(module_name):
    """Creates and configures a logger for a specific module."""
    logger = logging.getLogger(f"GradeAntPlus-{module_name}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # File handler
        log_file = LOG_DIR / f"{module_name}.log"
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Suppress noisy library logs
        for lib in ['google_adk', 'google.genai', 'httpx']:
            logging.getLogger(lib).setLevel(logging.WARNING)

    return logger

# ==============================================================================
# SECTION 2: FILE I/O UTILITIES
# ==============================================================================

def load_questions_from_file(filename: str) -> list:
    """
    Loads a list of questions from a JSON file, handling two possible formats.

    Format 1: The JSON root is a list of question objects.
    Format 2: The JSON root is a dictionary with a "questions" key containing the list.

    Returns the list of questions, or an empty list if an error occurs.
    """
    logger = get_logger(__name__)
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Case 1: The file's root is a list (the original format)
        if isinstance(data, list):
            logger.info(f"Successfully loaded {len(data)} questions from a direct list in '{filename}'.")
            return data

        # Case 2: The file's root is a dictionary (the new format)
        elif isinstance(data, dict):
            questions_list = data.get("questions")
            if isinstance(questions_list, list):
                logger.info(f"Successfully loaded {len(questions_list)} questions from the 'questions' key in '{filename}'.")
                return questions_list
            else:
                logger.error(f"Error: File '{filename}' is a dictionary but is missing a valid 'questions' list.")
                return []

        # Handle cases where the JSON is valid but not in an expected format
        else:
            logger.error(f"Error: Unsupported JSON format in '{filename}'. Root must be a list or a dictionary.")
            return []

    except FileNotFoundError:
        logger.error(f"Error: The file '{filename}' was not found.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error: The file '{filename}' contains invalid JSON.")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading '{filename}': {e}")
        return []