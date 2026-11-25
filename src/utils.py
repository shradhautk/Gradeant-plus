#!/usr/bin/env python3
# Module:  utils.py
# Version: 1.5.2
"""
================================================================================
GradeAnt+ · Tutoring Pipeline · Utilities
================================================================================

Title:       Logging, input loading and validation, session reports, and the
             GA-format converter
Author:      Dr. Agarwal's Research Team
Version:     1.5.2
Date:        2025-09-21

utils.py — shared helpers with no LLM code. Importing it does not load Gradio;
the converter UI imports it only when launched.

    python utils.py              self-check on data/input/qa.json
    python utils.py --convert    converter web UI on port 7860

PUBLIC INTERFACE
────────────────
    get_logger(name)                          -> Logger  (logs/gradeantplus.log)
    load_and_validate_questions(path)         -> list
    calculate_session_metrics(transcript)     -> dict
    create_enhanced_markdown_summary(summary, transcript, path)
    datetime_uuid(seed)                       -> str
    merge_json_files(hw_file, qp_file)        -> (message, json_text, out_path)
    save_json_file(merged_json, out_path)     -> (message, out_path)
    launch_converter_ui()

GA-FORMAT CONVERTER
───────────────────
    GradeAnt homework JSON (data/ga_format_input/) + QP rubric JSON
      -> one flat entry per question/subpart -> data/input/<name>_with_QP.json
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

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
        log_file = LOG_DIR / "gradeantplus.log"
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Suppress noisy library logs
        for lib in ['google_adk', 'google.genai', 'httpx']:
            logging.getLogger(lib).setLevel(logging.WARNING)

        logging.getLogger('google.generativeai').setLevel(logging.ERROR)
        logging.getLogger('google_adk').setLevel(logging.ERROR)
        logging.getLogger('google_genai').setLevel(logging.ERROR)
        
    return logger

logger = get_logger(__name__)

# ==============================================================================
# SECTION 2: INPUT VALIDATION
# ==============================================================================

def validate_question_format(question: dict) -> bool:
    """Validate that a question object has all required fields"""
    required_fields = ['question_id', 'question_text', 'student_answer', 'reference_answer']
    
    for field in required_fields:
        if field not in question:
            logger.error(f"Missing required field '{field}' in question: {question.get('question_id', 'Unknown')}")
            return False
        
        if not question[field] or not isinstance(question[field], str):
            logger.error(f"Invalid value for field '{field}' in question: {question.get('question_id', 'Unknown')}")
            return False
    
    return True

# ==============================================================================
# SECTION 3: FILE I/O UTILITIES
# ==============================================================================

def load_questions_from_file(filename: str) -> list:
    """
    Loads a list of questions from a JSON file, handling two possible formats.

    Format 1: The JSON root is a list of question objects.
    Format 2: The JSON root is a dictionary with a "questions" key containing the list.

    Returns the list of questions, or an empty list if an error occurs.
    """
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

def load_and_validate_questions(filename: str) -> list:
    """Enhanced question loading with validation"""
    questions = load_questions_from_file(filename)
    
    if not questions:
        return []
    
    # Validate each question
    valid_questions = []
    for i, question in enumerate(questions):
        if validate_question_format(question):
            valid_questions.append(question)
        else:
            logger.warning(f"Skipping invalid question at index {i}")
    
    logger.info(f"Loaded {len(valid_questions)} valid questions out of {len(questions)} total")
    return valid_questions

# ==============================================================================
# SECTION 4: SESSION ANALYTICS
# ==============================================================================

def calculate_session_metrics(transcript_data: List[dict]) -> Dict[str, Any]:
    """Calculate detailed session metrics for enhanced reporting"""
    if not transcript_data:
        return {}
    
    metrics = {
        "total_questions": len(transcript_data),
        "questions_requiring_feedback": 0,
        "questions_correct_first_try": 0,
        "total_conversation_turns": 0,
        "average_turns_per_feedback_session": 0,
        "common_mistake_categories": [],
        "key_physics_topics": [],
        "misconception_frequency": {},
        "concept_coverage": {},
    }
    
    feedback_sessions = 0
    total_feedback_turns = 0
    
    for transcript in transcript_data:
        knowledge_resp = transcript.get("knowledge_response", {})
        conversation = transcript.get("conversation_history", [])
        
        # Basic counts
        if knowledge_resp.get("needs_feedback", False):
            metrics["questions_requiring_feedback"] += 1
            feedback_sessions += 1
            
        if knowledge_resp.get("is_correct", False):
            metrics["questions_correct_first_try"] += 1
            
        # Conversation analysis
        conversation_turns = len(conversation) // 2 if conversation else 0
        metrics["total_conversation_turns"] += conversation_turns
        
        if conversation_turns > 0:
            total_feedback_turns += conversation_turns
        
        # Collect and analyze misconceptions
        misconceptions = knowledge_resp.get("misconceptions", [])
        for misconception in misconceptions:
            if misconception in metrics["misconception_frequency"]:
                metrics["misconception_frequency"][misconception] += 1
            else:
                metrics["misconception_frequency"][misconception] = 1
        
        # Collect and analyze key concepts
        key_concepts = knowledge_resp.get("key_concepts", [])
        for concept in key_concepts:
            if concept in metrics["concept_coverage"]:
                metrics["concept_coverage"][concept] += 1
            else:
                metrics["concept_coverage"][concept] = 1
        
        # Add to lists for summary
        metrics["common_mistake_categories"].extend(misconceptions)
        metrics["key_physics_topics"].extend(key_concepts)
    
    # Calculate averages
    if feedback_sessions > 0:
        metrics["average_turns_per_feedback_session"] = total_feedback_turns / feedback_sessions
    
    # Remove duplicates and sort by frequency
    metrics["common_mistake_categories"] = list(set(metrics["common_mistake_categories"]))
    metrics["key_physics_topics"] = list(set(metrics["key_physics_topics"]))
    
    # Calculate success rates
    if metrics["total_questions"] > 0:
        metrics["first_attempt_success_rate"] = (metrics["questions_correct_first_try"] / metrics["total_questions"]) * 100
        metrics["feedback_required_rate"] = (metrics["questions_requiring_feedback"] / metrics["total_questions"]) * 100
    
    return metrics

# ==============================================================================
# SECTION 5: ENHANCED MARKDOWN GENERATION
# ==============================================================================

async def create_markdown_summary(summary_data: Dict[str, Any], output_path: Path) -> None:
    """Creating readable markdown summary (original function maintained for compatibility)"""
    try:
        markdown_content = f"""# GradeAnt+ Session Summary

## Session Overview
{summary_data.get('session_overview', 'No overview available')}

## Key Concepts and Formulas
{summary_data.get('key_concepts_and_formulas', 'No concepts listed')}

## Common Misconceptions Addressed
{summary_data.get('common_misconceptions_addressed', 'No misconceptions noted')}

## Areas for Further Study
{summary_data.get('areas_for_further_study', 'No recommendations available')}

---
*Generated by GradeAnt+ on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logger.info(f"Markdown summary created: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to create markdown summary: {str(e)}")

async def create_enhanced_markdown_summary(summary_data: Dict[str, Any], transcript_data: List[dict], output_path: Path) -> None:
    """Create comprehensive markdown summary with detailed analytics"""
    
    try:
        # Calculate session metrics
        metrics = calculate_session_metrics(transcript_data)
        
        markdown_content = f"""# GradeAnt+ Comprehensive Session Report

## Session Analytics Dashboard
- **Total Questions Processed**: {metrics.get('total_questions', 0)}
- **Questions Requiring Interactive Feedback**: {metrics.get('questions_requiring_feedback', 0)}
- **Questions Correct on First Try**: {metrics.get('questions_correct_first_try', 0)}
- **First Attempt Success Rate**: {metrics.get('first_attempt_success_rate', 0):.1f}%
- **Interactive Learning Sessions**: {metrics.get('questions_requiring_feedback', 0)}
- **Total Conversation Turns**: {metrics.get('total_conversation_turns', 0)}
- **Average Turns per Feedback Session**: {metrics.get('average_turns_per_feedback_session', 0):.1f}

## Learning Journey Overview
{summary_data.get('session_overview', 'No overview available')}

## Physics Concepts & Formulas Mastered
{summary_data.get('key_concepts_and_formulas', 'No concepts listed')}

## Conceptual Breakthroughs & Misconceptions Resolved
{summary_data.get('common_misconceptions_addressed', 'No misconceptions noted')}

## Personalized Study Roadmap
{summary_data.get('areas_for_further_study', 'No recommendations available')}

"""

        # Add detailed question-by-question analysis
        if transcript_data:
            markdown_content += "## Detailed Question Analysis\n\n"
            
            for idx, transcript in enumerate(transcript_data, 1):
                question_data = transcript.get("question_data", {})
                knowledge_resp = transcript.get("knowledge_response", {})
                conversation = transcript.get("conversation_history", [])
                
                # Status indicators
                status_icon = "✅" if knowledge_resp.get("is_correct") else "🔄"
                feedback_needed = "Yes" if knowledge_resp.get("needs_feedback") else "No"
                
                markdown_content += f"""### Question {idx}: {question_data.get('question_id', 'Unknown')}

**Status**: {status_icon} {'Correct' if knowledge_resp.get('is_correct') else 'Needed Guidance'}  
**Interactive Session Required**: {feedback_needed}  
**Key Physics Concepts**: {', '.join(knowledge_resp.get('key_concepts', []))}  
"""

                # Add misconceptions if present
                misconceptions = knowledge_resp.get('misconceptions', [])
                if misconceptions:
                    markdown_content += f"**Conceptual Challenges Addressed**: {', '.join(misconceptions)}  \n"
                
                # Add conversation summary if present
                if conversation:
                    turns = len(conversation) // 2
                    markdown_content += f"**Interactive Learning Turns**: {turns}  \n"
                
                # Add confidence level
                confidence = knowledge_resp.get('confidence', 'Not specified')
                markdown_content += f"**Analysis Confidence**: {confidence}  \n\n"

        # Add concept frequency analysis
        concept_coverage = metrics.get('concept_coverage', {})
        if concept_coverage:
            markdown_content += "## Physics Concept Frequency Analysis\n\n"
            sorted_concepts = sorted(concept_coverage.items(), key=lambda x: x[1], reverse=True)
            for concept, frequency in sorted_concepts[:10]:  # Top 10
                markdown_content += f"- **{concept}**: Appeared in {frequency} question(s)\n"
            markdown_content += "\n"

        # Add misconception frequency analysis  
        misconception_freq = metrics.get('misconception_frequency', {})
        if misconception_freq:
            markdown_content += "## Common Challenge Patterns\n\n"
            sorted_misconceptions = sorted(misconception_freq.items(), key=lambda x: x[1], reverse=True)
            for misconception, frequency in sorted_misconceptions:
                markdown_content += f"- **{misconception}**: Occurred {frequency} time(s)\n"
            markdown_content += "\n"

        # Footer with usage guidance
        markdown_content += f"""
---
*Generated by GradeAnt+ AI Tutoring System on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## How to Use This Report

### For Immediate Review
1. **Check your Success Rate** in the Analytics Dashboard
2. **Review Conceptual Breakthroughs** to reinforce new understanding
3. **Focus on Personalized Study Roadmap** for targeted improvement

### For Long-term Learning
1. **Study the Detailed Question Analysis** to understand your problem-solving patterns
2. **Review Physics Concept Frequency** to identify your strongest areas
3. **Address Challenge Patterns** to prevent recurring mistakes

### Next Steps
- Practice additional problems in areas highlighted in the Study Roadmap
- Revisit concepts that appeared in multiple misconceptions
- Celebrate your progress - learning physics takes time and persistence!

**Remember**: This AI analysis is designed to support your learning journey. Each "mistake" is actually a learning opportunity that brings you closer to mastery.
"""
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logger.info(f"Enhanced markdown summary created: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to create enhanced markdown summary: {str(e)}")


def datetime_uuid(seed:str):
    """Generate a datetime-based unique identifier"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M')}_{seed}"

# ==============================================================================
# SECTION 6: GA-FORMAT CONVERTER (GradeAnt output + QP rubric -> GradeAnt+ input)
# Formerly src/xjson_converter.py. Launch the web UI with: python utils.py --convert
# ==============================================================================

GA_FORMAT_INPUT_FOLDER = Path(__file__).parent.parent / "data" / "ga_format_input"
MERGED_INPUT_FOLDER = Path(__file__).parent.parent / "data" / "input"

def has_key_recursive(data, key):
    """Recursively check if the key exists at any level in the JSON structure."""
    if isinstance(data, dict):
        if key in data:
            return True
        return any(has_key_recursive(value, key) for value in data.values())
    elif isinstance(data, list):
        return any(has_key_recursive(item, key) for item in data)
    return False

def find_subparts_recursive(data, subparts=None, parent_key=None):
    """Recursively find all dictionaries containing a 'subpart' key."""
    if subparts is None:
        subparts = []
    
    if isinstance(data, dict):
        if "subpart" in data:
            subparts.append(data)
        for key, value in data.items():
            find_subparts_recursive(value, subparts, key)
    elif isinstance(data, list):
        for item in data:
            find_subparts_recursive(item, subparts, parent_key)
    
    return subparts

def merge_json_files(hw_file, qp_file):
    # Check if files are uploaded
    if hw_file is None or qp_file is None:
        return "Error: Please upload both HW and QP files.", None, None

    try:
        # Load the HW and QP JSON files
        with open(hw_file.name, 'r', encoding='utf-8') as hw_file_handle:
            hw_data = json.load(hw_file_handle)

        with open(qp_file.name, 'r', encoding='utf-8') as qp_file_handle:
            qp_data = json.load(qp_file_handle)

        # Validate HW file for 'reply' key
        if not has_key_recursive(hw_data, "reply"):
            return "Error: HW file missing 'reply' key at any level.\nPlease re-upload the HW file.", None, None

        # Validate QP file for 'standard_answer' key
        if not has_key_recursive(qp_data, "standard_answer"):
            return "Error: QP file missing 'standard_answer' key at any level.\nPlease re-upload the QP file.", None, None

        # Initialize the merged JSON structure
        merged_data = {
            "homework": hw_data.get("homework", ""),
            "questions": []
        }

        # Process each question in HW
        hw_questions = hw_data.get("questions", [])
        qp_questions = qp_data.get("questions", [])
        
        if not hw_questions:
            return "Error: No questions found in HW file.", None, None
        if not qp_questions:
            return "Error: No questions found in QP file.", None, None

        for hw_question in hw_questions:
            question_number = hw_question.get("question_number")
            if not question_number:
                continue  # Skip if no question_number
            
            # Find matching QP question
            qp_question = next((q for q in qp_questions if q.get("question_number") == question_number), None)
            if not qp_question:
                print(f"Warning: No matching QP question found for question {question_number}")
                continue  # Skip if no matching QP question

            # Check if questions have subparts
            hw_has_subparts = "subparts" in hw_question and hw_question["subparts"]
            qp_has_subparts = "subparts" in qp_question and qp_question["subparts"]

            if hw_has_subparts and qp_has_subparts:
                # Handle questions with subparts
                hw_subparts = hw_question["subparts"]
                qp_subparts = qp_question["subparts"]
                processed_subparts = set()  # Track processed subparts to avoid duplicates
                
                for hw_subpart in hw_subparts:
                    subpart_letter = hw_subpart.get("subpart")
                    if not subpart_letter or subpart_letter in processed_subparts:
                        continue  # Skip if no subpart letter or already processed
                    
                    processed_subparts.add(subpart_letter)
                    
                    # Find matching QP subpart
                    qp_subpart = next((q for q in qp_subparts if q.get("subpart") == subpart_letter), None)
                    if not qp_subpart:
                        print(f"Warning: No matching QP subpart found for question {question_number}, subpart {subpart_letter}")
                        continue  # Skip if no matching QP subpart

                    # Create new question_number (e.g., 2a, 3b)
                    new_question_number = f"{question_number}{subpart_letter}"
                    
                    # Use the description from the subpart directly
                    full_description = hw_subpart.get("description", "")

                    # Ensure required fields exist
                    required_hw_fields = ["description", "reply"]
                    required_qp_fields = ["description", "standard_answer", "max_marks", "rubric"]
                    
                    missing_hw_fields = [field for field in required_hw_fields if field not in hw_subpart or not hw_subpart[field]]
                    missing_qp_fields = [field for field in required_qp_fields if field not in qp_subpart or not qp_subpart[field]]
                    
                    if missing_hw_fields or missing_qp_fields:
                        error_msg = f"Error: Missing required fields in Question {question_number} subpart {subpart_letter}."
                        if missing_hw_fields:
                            error_msg += f"\nMissing from HW: {', '.join(missing_hw_fields)}"
                        if missing_qp_fields:
                            error_msg += f"\nMissing from QP: {', '.join(missing_qp_fields)}"
                        error_msg += "\nPlease re-upload the file(s)."
                        return error_msg, None, None

                    question_entry = {
                        "question_id": f"q{new_question_number}",
                        "question_text": full_description,
                        "student_answer": hw_subpart["reply"],
                        "reference_answer": qp_subpart["standard_answer"],
                        "max_marks": qp_subpart["max_marks"],
                        "rubric": qp_subpart["rubric"]
                    }
                    merged_data["questions"].append(question_entry)
            else:
                # Handle questions without subparts
                required_hw_fields = ["description", "reply"]
                required_qp_fields = ["description", "max_marks", "standard_answer", "rubric"]
                
                missing_hw_fields = [field for field in required_hw_fields if field not in hw_question or not hw_question[field]]
                missing_qp_fields = [field for field in required_qp_fields if field not in qp_question or not qp_question[field]]
                
                if missing_hw_fields or missing_qp_fields:
                    error_msg = f"Error: Missing required fields in Question {question_number}."
                    if missing_hw_fields:
                        error_msg += f"\nMissing from HW: {', '.join(missing_hw_fields)}"
                    if missing_qp_fields:
                        error_msg += f"\nMissing from QP: {', '.join(missing_qp_fields)}"
                    error_msg += "\nPlease re-upload the file(s)."
                    return error_msg, None, None

                question_entry = {
                    "question_id": f"q{question_number}",
                    "question_text": hw_question["description"],
                    "student_answer": hw_question["reply"],
                    "reference_answer": qp_question["standard_answer"],
                    "max_marks": qp_question["max_marks"],
                    "rubric": qp_question["rubric"]
                }
                merged_data["questions"].append(question_entry)

        # Check if any questions were processed
        if not merged_data["questions"]:
            return "Error: No valid questions could be merged. Please check your input files.", None, None

        # Generate output filename
        output_filename = MERGED_INPUT_FOLDER / f'{os.path.splitext(os.path.basename(hw_file.name))[0]}_with_QP.json'

        # Return success message, JSON content, and output filename
        success_msg = f"Successfully merged {len(merged_data['questions'])} questions.\nReady to save to: {output_filename}"
        return success_msg, json.dumps(merged_data, indent=2), str(output_filename)

    except FileNotFoundError as e:
        return f"Error: One or both files not found. Please check the uploaded files.\n{e}", None, None
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON format in one or both files.\n{e}", None, None
    except Exception as e:
        return f"Error: {str(e)}", None, None

def save_json_file(merged_json, output_filename):
    """Save the merged JSON data to the output folder."""
    try:
        # Ensure output folder exists
        if not MERGED_INPUT_FOLDER.exists():
            MERGED_INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        
        # Save the merged JSON to the output folder
        with open(output_filename, 'w', encoding='utf-8') as merged_file:
            # FIX: removed json.loads(), as Gradio passes a Python dict here
            json.dump(merged_json, merged_file, indent=2, ensure_ascii=False)
        
        return f"File successfully saved to: {output_filename}", output_filename
    except PermissionError as e:
        return f"Error: Permission denied when saving file. Check folder permissions.\n{e}", None
    except Exception as e:
        return f"Error: {str(e)}", None

def launch_converter_ui():
    """Build and launch the Gradio UI for merging HW and QP JSON files (port 7860)."""
    import gradio as gr  # imported lazily so other modules importing utils don't load Gradio

    MERGED_INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    print("Files available in 'ga_format_input' folder:")
    if GA_FORMAT_INPUT_FOLDER.exists():
        print(os.listdir(GA_FORMAT_INPUT_FOLDER))
    else:
        print("Input folder does not exist.")

    # Create Gradio interface
    with gr.Blocks(title="JSON File Merger") as demo:
        gr.Markdown("## Merge Homework and Question Paper JSON Files")
        gr.Markdown(
            f"""
            **Instructions:**
            - Upload Homework (HW) and Question Paper (QP) JSON files
            - HW file must contain 'reply' key at any level
            - QP file must contain 'standard_answer' key at any level
            - Subparts will be converted to main questions in the merged file
            - Files will be validated before merging
            - After merging, click 'Save to Output Folder' to save the merged file

            **File Locations:**
            - Input HW & QP files should be from: `{GA_FORMAT_INPUT_FOLDER}`
            - Merged QA file will be saved to: `{MERGED_INPUT_FOLDER}`
            """
        )

        with gr.Row():
            with gr.Column():
                hw_input = gr.File(label="Upload Homework JSON File", file_types=[".json"])
            with gr.Column():
                qp_input = gr.File(label="Upload Question Paper JSON File", file_types=[".json"])

        submit_button = gr.Button("Merge Files", variant="primary")

        with gr.Row():
            output_json = gr.JSON(label="Merged JSON Output")

        with gr.Row():
            output_message = gr.Textbox(label="Merge Status")
            output_filename_state = gr.State()

        with gr.Row():
            save_button = gr.Button("Save to Output Folder", variant="secondary")

        with gr.Row():
            download_file = gr.File(label="Download Merged JSON File")
            save_message = gr.Textbox(label="Save Status")

        submit_button.click(
            fn=merge_json_files,
            inputs=[hw_input, qp_input],
            outputs=[output_message, output_json, output_filename_state]
        )

        save_button.click(
            fn=save_json_file,
            inputs=[output_json, output_filename_state],
            outputs=[save_message, download_file]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)

# ==============================================================================
# SECTION 7: COMPATIBILITY TEST / CLI
# ==============================================================================

if __name__ == "__main__":
    if "--convert" in sys.argv:
        launch_converter_ui()
        sys.exit(0)

    INPUT_FOLDER = Path(__file__).parent.parent / "data" / "input"
    qa_file_path = INPUT_FOLDER / "qa.json"
    
    # Test the enhanced validation
    input_questions = load_and_validate_questions(qa_file_path)
    if input_questions:
        print(f"Successfully validated {len(input_questions)} questions")
        
        # Test metrics calculation with dummy data
        dummy_transcript = [{
            "question_data": {"question_id": "test1"},
            "knowledge_response": {
                "is_correct": True,
                "needs_feedback": False,
                "misconceptions": ["test misconception"],
                "key_concepts": ["Newton's Laws"],
                "confidence": "high"
            },
            "conversation_history": []
        }]
        
        metrics = calculate_session_metrics(dummy_transcript)
        print("Metrics calculation test:", metrics)
        
    else:
        print("No valid questions found in test file")