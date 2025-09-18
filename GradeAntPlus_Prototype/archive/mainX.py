# ==============================================================================
# SECTION 1: IMPORTS
# ==============================================================================
import uuid
import json
import asyncio
import os
from pathlib import Path
import pprint
import shutil

from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from agents import question_pipeline, summary_pipeline
from utils import get_logger, load_questions_from_file

logger = get_logger(__name__)

proj_dir = Path(__file__).parent.parent
INPUT_FOLDER = proj_dir / "data" / "input"
OUTPUT_FOLDER = proj_dir / "data" / "output"

# ==============================================================================
# SECTION 2: FUNCTIONS
# ==============================================================================

# --- Function 1: Process Question Loop ---
async def process_question_loop(question_runner: Runner, service: InMemorySessionService, session_id: str, user_id: str, input_questions: list):
    """
    Loops through each question, runs the question_processor agent, and stores the transcript.
    """
    # Looping through each question from the input file.
    for idx, question_data in enumerate(input_questions, 1):
        print(f"\n{'='*100}")
        print(f"Processing Question {idx}/{len(input_questions)}: {question_data.get('question_id', 'UNKNOWN')}")
        print(f"{'='*100}")
        
        # Displaying the current question's data on the console.
        print("\n📋 INITIAL INPUT DATA:")
        input_keys = ["question_id", "question_text", "student_answer", "reference_answer"]
        for key in input_keys:
            value = question_data.get(key, "NOT FOUND")
            print('-'*100)
            if key=='question_id':
                print(f"{key}: {value}")
            else:
                print(f"**{key}**:\n{value}")
        
        # Getting the current session to update it with new question data.
        session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        current_question_state = question_data.copy()
        current_question_state["conversation_history"] = [] # Resetting conversation history.
        
        # Injecting the current question's data.
        session.state.update(current_question_state)
        await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)

        # Creating the initial message that triggers the agent run.
        initial_msg = types.Content(role="user", parts=[types.Part(text="Process this question.")])
        
        print("\n🚀 Starting processing pipeline...")
        
        # Executing the per-question agent orchestrator and listening for events.
        async for event in question_runner.run_async(user_id=user_id, session_id=session_id, new_message=initial_msg):
            if hasattr(event, 'author') and event.author: # Logging every agent event for debugging.
                logger.info(f"Event from {event.author}")
            
            if (event.is_final_response() and 
                event.author == "CorrectAnswerAgent" and 
                event.content):
                print(f"\n🎉 GradeAnt+ Says: {event.content.parts[0].text}")
        
        # After processing, saving the results for this question.
        print("\n💾 Saving transcript for this question...")
        session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        
        # Creating the transcript object.
        transcript_object = {
            "question_data": question_data,
            "knowledge_response": session.state.get("knowledge_response"),
            "conversation_history": session.state.get("conversation_history")
        }
        
        # Appending the transcript object to the full transcript.
        full_transcript = session.state.get("full_transcript", [])
        full_transcript.append(transcript_object)
        session.state["full_transcript"] = full_transcript
        
        # Saving the session state.
        await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)
        print(f"Transcript saved. Total transcripts stored: {len(full_transcript)}")
        
        print(f"\n✅ Finished Processing Question {idx}: {question_data.get('question_id', 'UNKNOWN')}")


# --- Function 2: Generate Final Report ---
async def generate_final_report(summary_runner: Runner, service: InMemorySessionService, session_id: str, user_id: str):
    """
    Runs the summary pipeline and saves the final report to a file and prints it.
    """
    print("\n" + "="*100)
    print("ALL QUESTIONS PROCESSED: Generating final report and audio summary...")
    print("="*100)
    
    # Creating a trigger message for the summary pipeline.
    summary_msg = types.Content(role="user", parts=[types.Part(text="Generate the final summary and audio.")])
    # Executing the summary pipeline runner.
    async for event in summary_runner.run_async(user_id=user_id, session_id=session_id, new_message=summary_msg):
        if event.is_final_response():
            logger.info(f"Summary pipeline event from: {event.author}")

    # Retrieving the final session state containing all generated artifacts.
    final_session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
    full_transcript = final_session.state.get("full_transcript", [])
    final_summary = final_session.state.get("final_summary")
    tts_output = final_session.state.get("tts_output", {})

    #Checking if the audio file path is a string
    audio_file_path = tts_output.get("audio_file_path") if isinstance(tts_output, dict) else None

    if full_transcript:
        # Creating the final report object.
        final_report = {
            "session_summary": final_summary,
            "audio_summary_path": audio_file_path,
            "detailed_transcript": full_transcript
        }

        # Saving the final report to a file.
        output_file_path = OUTPUT_FOLDER / f"session_report_{session_id}.json"
        output_audio_path = OUTPUT_FOLDER / f"audio_summary_{session_id}.mp3"
        try:
            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_report, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Final report successfully saved to:\n   {output_file_path}")
        except Exception as e:
            print(f"\n❌ Error saving report to file: {e}")

        print("\n" + "-"*50)
        print("FINAL SUMMARY (CONSOLE PREVIEW):")
        print("-"*50)
        if final_summary:
            pprint.pprint(final_summary)
        else:
            print("\n⚠️ Summary could not be generated.")
        
        if audio_file_path:
            print(f"\n🔊 Audio summary successfully saved to:\n   {audio_file_path}")
            shutil.move(audio_file_path, output_audio_path)
        else:
            print("\n🔇 Audio summary could not be generated.")
    else:
        print("\n⚠️ No transcripts were generated during the session.")


# --- Function 3: Main Orchestrator ---
async def grade_ant_plus_main(input_questions: list, session_id: str = None, user_id: str = None):
    """
    The main orchestrator function for the GradeAnt+ application.
    """
    if not input_questions:
        print("No questions loaded. Exiting.")
        return
    
    if not session_id:
        session_id = str(uuid.uuid4())
    if not user_id:
        user_id = "student123"
    
    # 1. Initialization
    service = InMemorySessionService()
    question_runner = Runner(agent=question_pipeline, session_service=service, app_name="GradeAntPlus")
    summary_runner = Runner(agent=summary_pipeline, session_service=service, app_name="GradeAntPlus")
    
    print("--- Starting GradeAnt+ Session (with Interactive Feedback) ---")
    print(f"📊 Total questions to process: {len(input_questions)}")

    # 2. Session Initialization
    
    # Creating the initial session state.
    await service.create_session(
        app_name="GradeAntPlus", 
        user_id=user_id, 
        session_id=session_id, 
        state={"full_transcript": []}
    )

    # 2. Per-Question Processing
    await process_question_loop(question_runner, service, session_id, user_id, input_questions)

    # 3. Final Report Generation
    await generate_final_report(summary_runner, service, session_id, user_id)


# ==============================================================================
# SECTION 7: MAIN APPLICATION
# ==============================================================================
async def main():
    # qa_file_path = INPUT_FOLDER / "Narrie_HW3_with_QP.json"
    qa_file_path = INPUT_FOLDER / "qa.json"
    
    #session id will consist of qa_file_path.name.split(".")[0] and a random uuid
    session_id = f"{qa_file_path.name.split(".")[0]}_{str(uuid.uuid4())}"
    user_id = "Narrie"
    
    input_questions = load_questions_from_file(qa_file_path)
    if input_questions:
        await grade_ant_plus_main(input_questions, session_id=session_id, user_id=user_id)
        print("\n--- All questions processed. Session complete. ---")
    else:
        print("\n--- No questions found. ---")
# ==============================================================================
if __name__ == "__main__":
    os.system('clear')
    asyncio.run(main())