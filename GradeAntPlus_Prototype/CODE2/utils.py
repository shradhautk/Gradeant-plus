import json
import logging
import os
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

# ==============================================================================
# SECTION 6: COMPATIBILITY TEST
# ==============================================================================

if __name__ == "__main__":
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