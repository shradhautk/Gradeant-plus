import uuid
import json
import asyncio
import os
from pathlib import Path
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from agents import root_agent
from utils import get_logger, load_questions_from_file
logger = get_logger(__name__)

proj_dir = Path(__file__).parent.parent  # as the file is in code directory
INPUT_FOLDER = proj_dir / "data" / "input"
OUTPUT_FOLDER = proj_dir / "data" / "output"

# ==============================================================================
# SECTION 6: AGENT RUNNER
# ==============================================================================
async def grade_ant_plus_main(input_questions: list):
    """Main function uses the master orchestrator to run the full process."""
    
    if not input_questions:
        return
    
    service = InMemorySessionService()
    runner = Runner(
        agent=root_agent, 
        session_service=service, 
        app_name="GradeAntPlus"
    )
    
    print("--- Starting GradeAnt+ Session (with Interactive Feedback) ---")
    print(f"📊 Total questions to process: {len(input_questions)}")

    for idx, question_data in enumerate(input_questions, 1):
        print(f"\n{'='*100}")
        print(f"Processing Question {idx}/{len(input_questions)}: {question_data.get('question_id', 'UNKNOWN')}")
        print(f"{'='*100}")
        
        # Print all input data at the start
        print("\n📋 INITIAL INPUT DATA:")
        input_keys = ["question_id", "student_answer", "reference_answer", "question_text"]
        
        for key in input_keys:
            value = question_data.get(key, "NOT FOUND")
            print("-"*100)
            # if len(str(value)) > 200:
            #     print(f"  {key}: {str(value)[:200]}...")
            # else:
            print(f"**{key}**:\n{value}")
        
        session_id = str(uuid.uuid4())
        
        # Initialize session state with question data and an empty conversation history
        initial_state = question_data.copy()
        initial_state["conversation_history"] = []
        
        await service.create_session(
            app_name="GradeAntPlus", 
            user_id="student123", 
            session_id=session_id, 
            state=initial_state
        )

        initial_msg = types.Content(
            role="user", 
            parts=[types.Part(text="Process this question.")]
        )
        
        print("\n🚀 Starting processing pipeline...")
        
        # The main loop is now very clean. The orchestrator and tools handle everything.
        async for event in runner.run_async(
            user_id="student123", 
            session_id=session_id, 
            new_message=initial_msg
        ):
            # Log agent events for debugging
            if hasattr(event, 'author') and event.author:
                logger.info(f"Event from {event.author}")
            
            # We only need to catch the one-shot praise message here.
            if (event.is_final_response() and 
                event.author == "CorrectAnswerAgent" and 
                event.content):
                print(f"\n🎉 GradeAnt+ Says: {event.content.parts[0].text}")
        
        print(f"\n✅ Finished Processing Question {idx}: {question_data.get('question_id', 'UNKNOWN')}")
        #print("-" * 60)


# ==============================================================================
# SECTION 7: MAIN APPLICATION
# ==============================================================================
async def main():
    
    qa_file_path = INPUT_FOLDER / "Narrie_HW3_with_QP.json"
    input_questions = load_questions_from_file(qa_file_path)
    if input_questions:
        await grade_ant_plus_main(input_questions)
        print("\n--- All questions processed. Session complete. ---")
    else:
        print("\n--- No questions found. ---")

if __name__ == "__main__":
    os.system('clear')
    asyncio.run(main())