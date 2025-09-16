import uuid
import json
import asyncio
import logging
from typing import List

# --- Pydantic and ADK Imports ---
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('GradeAntPlus-Step1')

# NEW: Suppress noisy internal warnings from the libraries
logging.getLogger('google_adk').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.ERROR)


# ==============================================================================
# SECTION 1: PYDANTIC OUTPUT SCHEMA
# ==============================================================================

class KnowledgeResponse(BaseModel):
    """Defines the structured output for the KnowledgeAgent."""
    is_correct: bool = Field(description="True if the student's answer is fundamentally correct, otherwise False.")
    needs_feedback: bool = Field(description="True if the student could benefit from guided feedback, even if partially correct.")
    misconceptions: List[str] = Field(description="A list of specific conceptual errors in the student's reasoning.")
    missing_steps: List[str] = Field(description="A list of important logical or calculation steps the student omitted.")
    key_concepts: List[str] = Field(description="A list of the core physics concepts relevant to the question.")
    hint: str = Field(description="A single, gentle Socratic question to guide the student if feedback is needed.")
    confidence: str = Field(description="Confidence in the evaluation, can be 'high', 'medium', or 'low'.")

# ==============================================================================
# SECTION 2: AGENT DEFINITION
# ==============================================================================

KNOWLEDGE_AGENT_INSTRUCTION = """You are a physics expert analyzing a student's response. You must evaluate the student's answer against the provided reference answer and the underlying physics principles.

**Your Task:**
Your output must be a JSON object that strictly conforms to the required schema. Analyze the following data:
- Student Answer: {student_answer}
- Reference Answer: {reference_answer}

**Evaluation Guidelines:**
- Set "is_correct" to true only if the final answer and reasoning are both sound.
- Set "needs_feedback" to true if there are any conceptual gaps, even if the final number is correct.
- Be specific and concise in your lists of misconceptions and missing steps.
"""

knowledge_agent = LlmAgent(
    # NEW: Use the specified model
    model="gemini-2.5-flash",
    name="KnowledgeAgent",
    instruction=KNOWLEDGE_AGENT_INSTRUCTION,
    output_schema=KnowledgeResponse,
    output_key="knowledge_response"
)

# ==============================================================================
# SECTION 3: MAIN APPLICATION LOGIC
# ==============================================================================

def load_questions_from_file(filename: str) -> list:
    """Loads the list of questions from a JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not load questions from '{filename}': {e}")
        return []

async def grade_ant_plus_main():
    """Main function to run the KnowledgeAgent for each question."""
    service = InMemorySessionService()
    runner = Runner(agent=knowledge_agent, session_service=service, app_name="GradeAntPlus")

    input_questions = load_questions_from_file("qa.json")
    if not input_questions:
        print("No questions found in qa.json. Exiting.")
        return

    print("--- Starting Analysis by Knowledge Agent ---")

    for question_data in input_questions:
        print(f"\n{'='*25} Processing Question: {question_data['question_id']} {'='*25}")
        
        # NEW: Print the input data for clarity
        print(f"\n[Q] Question: {question_data.get('question_text', 'N/A')}")
        print(f"[A] Student's Answer: {question_data.get('student_answer', 'N/A')}")
        print(f"[R] Reference Answer: {question_data.get('reference_answer', 'N/A')}")
        print("-" * 50)
        
        session_id = str(uuid.uuid4())
        
        await service.create_session(
            app_name="GradeAntPlus",
            user_id="student123",
            session_id=session_id,
            state=question_data
        )
        
        initial_msg = types.Content(role="user", parts=[types.Part(text="Evaluate this answer.")])

        async for event in runner.run_async(user_id="student123", session_id=session_id, new_message=initial_msg):
            if event.is_final_response():
                final_session = await service.get_session(app_name="GradeAntPlus", user_id="student123", session_id=session_id)
                knowledge_response_dict = final_session.state.get("knowledge_response")
                
                if isinstance(knowledge_response_dict, dict):
                    print("--- Analysis Complete ---")
                    response_model = KnowledgeResponse(**knowledge_response_dict)
                    print(response_model.model_dump_json(indent=2))
                else:
                    print("--- Error: Analysis failed ---")
                    print(f"Expected a dictionary in the state, but got: {type(knowledge_response_dict)}")
                    print(f"Raw output: {knowledge_response_dict}")

if __name__ == "__main__":
    asyncio.run(grade_ant_plus_main())
    print("\n--- All questions processed. ---")