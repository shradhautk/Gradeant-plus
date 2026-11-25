#!/usr/bin/env python3
# Module:  main.py
# Version: 1.6.2
"""
================================================================================
GradeAnt+ · Tutoring Pipeline · Entry Point
================================================================================

Title:       Session runner — per-question tutoring loop and final report
Author:      Dr. Agarwal's Research Team
Version:     1.6.2
Date:        2025-09-21

main.py — runs one tutoring session for one student over a merged QA file.

    python main.py              (input: data/input/qa.json, set in main())
    python main.py --dry-run    no API calls, no key needed: canned agent
                                responses exercise loading, routing and reports

PUBLIC INTERFACE
────────────────
    grade_ant_plus_main(input_questions, session_id=None, user_id=None)
    dry_run_session(input_questions, session_id, user_id)
    process_question_loop(question_runner, service, session_id, user_id, questions)
    generate_final_report(summary_runner, service, session_id, user_id)

OUTPUTS (data/output/)
──────────────────────
    StructuredLog_Session<id>.json   full transcript + summary
    SummaryReport_Session<id>.md     study guide
    SummaryAudio_Session<id>.mp3     audio summary
    (dry runs add "_dryrun" to <id> and write no audio)
"""
from __future__ import annotations  # ADK type hints stay unevaluated, so --dry-run needs no ADK import

# ==============================================================================
# SECTION 1: IMPORTS
# ==============================================================================
import argparse
import uuid
import json
import asyncio
import os
from pathlib import Path
import pprint
import shutil
from datetime import datetime

# Live-run dependencies (Google ADK, Gemini, agents.py) are imported inside the
# functions that use them, so a --dry-run works without them or an API key.
from utils import get_logger, load_and_validate_questions, create_enhanced_markdown_summary, datetime_uuid

logger = get_logger(__name__)

proj_dir = Path(__file__).parent.parent
INPUT_FOLDER = proj_dir / "data" / "input"
OUTPUT_FOLDER = proj_dir / "data" / "output"
#DB_FOLDER = proj_dir / "data" / "sessionDb"
for folder in [OUTPUT_FOLDER]:#, DB_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# SECTION 2: FUNCTIONS
# ==============================================================================

# --- Function 1: Process Question Loop ---
async def process_question_loop(question_runner: Runner, service: InMemorySessionService, session_id: str, user_id: str, input_questions: list):
    """
    Loops through each question, runs the question_processor agent, and stores the transcript.
    """
    from google.genai import types
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
            
            # --- Enhanced logging for Knowledge Agent ---
            if (event.is_final_response() and
                event.author == "KnowledgeAgent" and
                event.content and event.content.parts):
                
                print("\n" + "-"*40)
                print("🧠 KNOWLEDGE AGENT ANALYSIS 🧠")
                print("-"*40)
                
                knowledge_response_dict = event.content.parts[0].text
                print(knowledge_response_dict)
                print("-"*40)

            # --- Enhanced logging for Interactive Teaching Agent ---
            if (event.is_final_response() and
                event.author == "InteractiveTeachingAgent" and
                event.content and event.content.parts):
                
                print("\n" + "-"*40)
                print("🎓 INTERACTIVE LEARNING SESSION COMPLETED 🎓")
                print("-"*40)
                
                teaching_response_dict = event.content.parts[0].text
                print(teaching_response_dict)
                print("-"*40)

            # --- Enhanced logging for Correct Answer Agent ---
            if (event.is_final_response() and 
                event.author == "CorrectAnswerAgent" and 
                event.content):
                print(f"\n🎉 GradeAnt+ Feedback: {event.content.parts[0].text}")
        
        # After processing, saving the results for this question.
        print("\n💾 Saving comprehensive transcript for this question...")
        session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        
        # Creating the enhanced transcript object with additional metadata
        transcript_object = {
            "question_data": question_data,
            "knowledge_response": session.state.get("knowledge_response"),
            "conversation_history": session.state.get("conversation_history"),
            "teaching_response": session.state.get("teaching_response") if session.state.get("teaching_response") else None,
            "processing_timestamp": datetime.now().isoformat(),  # Fixed: direct datetime usage
            "question_index": idx
        }
        
        # Appending the transcript object to the full transcript.
        full_transcript = session.state.get("full_transcript", [])
        full_transcript.append(transcript_object)
        session.state["full_transcript"] = full_transcript
        
        # Saving the session state.
        await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)
        print(f"Enhanced transcript saved. Total transcripts: {len(full_transcript)}")
        
        print(f"\n✅ Finished Processing Question {idx}: {question_data.get('question_id', 'UNKNOWN')}")


# --- Function 2: Generate Final Report ---
async def generate_final_report(summary_runner: Runner, service: InMemorySessionService, session_id: str, user_id: str):
    """
    Runs the summary pipeline and saves the final report to a file and prints it.
    Enhanced with better analytics and reporting.
    """
    from google.genai import types
    print("\n" + "="*100)
    print("ALL QUESTIONS PROCESSED: Generating comprehensive final report and audio summary...")
    print("="*100)
    
    # Define consistent file naming upfront
    base_filename = f"{session_id}"
    output_report_path = OUTPUT_FOLDER / f"StructuredLog_Session{base_filename}.json"
    output_audio_path = OUTPUT_FOLDER /  f"SummaryAudio_Session{base_filename}.mp3"
    summary_report_path = OUTPUT_FOLDER /f"SummaryReport_Session{base_filename}.md"
    
    # Update session state with the target audio path so TTS agent can use it
    session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
    session.state["target_audio_path"] = str(output_audio_path)
    await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)
    
    # Creating a trigger message for the summary pipeline.
    summary_msg = types.Content(role="user", parts=[types.Part(text="Generate the final summary and audio.")])
    
    print("🔄 Running AI summarization and audio generation pipeline...")
    
    # Executing the summary pipeline runner.
    async for event in summary_runner.run_async(user_id=user_id, session_id=session_id, new_message=summary_msg):
        if event.is_final_response():
            logger.info(f"Summary pipeline event from: {event.author}")
            if event.author == "SummarizationAgent":
                print("📊 Educational analysis completed")
            elif event.author == "AudioScriptAgent":
                print("📝 Podcast script generated")
            elif event.author == "TtsAgent":
                print("🔊 Audio conversion completed")

    # Retrieving the final session state containing all generated artifacts.
    final_session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
    full_transcript = final_session.state.get("full_transcript", [])
    final_summary = final_session.state.get("final_summary")
    tts_output = final_session.state.get("tts_output", {})
    
    # Handle audio file path more robustly
    generated_audio_path = None
    if isinstance(tts_output, dict):
        generated_audio_path = tts_output.get("audio_file_path")
    
    # Determine final audio path
    final_audio_path = None
    if generated_audio_path and os.path.exists(generated_audio_path):
        # If the generated audio path is different from target, move it
        if generated_audio_path != str(output_audio_path):
            try:
                OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
                shutil.move(generated_audio_path, output_audio_path)
                final_audio_path = str(output_audio_path)
                print(f"🔊 Audio file moved to: {final_audio_path}")
            except Exception as e:
                print(f"⚠️ Warning: Could not move audio file: {e}")
                final_audio_path = generated_audio_path
        else:
            final_audio_path = generated_audio_path
    
    if full_transcript:
        # Creating the enhanced final report object
        final_report = {
            "session_metadata": {
                "session_id": session_id,
                "user_id": user_id,
                "total_questions": len(full_transcript),
                "generation_timestamp": datetime.now().isoformat(),
                "ai_model_used": "gemini-2.0-flash"
            },
            "session_summary": final_summary,
            "audio_summary_path": final_audio_path,
            "detailed_transcript": full_transcript
        }

        # Saving the comprehensive final report to a file.
        try:
            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
            with open(output_report_path, 'w', encoding='utf-8') as f:
                json.dump(final_report, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Comprehensive session report saved to:\n   {output_report_path}")
        except Exception as e:
            print(f"\n❌ Error saving report to file: {e}")

        # Generate enhanced markdown summary
        try:
            await create_enhanced_markdown_summary(final_summary, full_transcript, summary_report_path)
            print(f"📝 Enhanced markdown summary saved to:\n   {summary_report_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not create enhanced markdown summary: {e}")
            # Fallback to basic markdown summary
            from utils import create_markdown_summary
            await create_markdown_summary(final_summary, summary_report_path)
            print(f"📝 Basic markdown summary saved to:\n   {summary_report_path}")

        print("\n" + "-"*50)
        print("FINAL EDUCATIONAL SUMMARY (CONSOLE PREVIEW):")
        print("-"*50)
        if final_summary:
            pprint.pprint(final_summary)
        else:
            print("\n⚠️ Summary could not be generated.")
        
        # Audio status reporting
        if final_audio_path and os.path.exists(final_audio_path):
            file_size = os.path.getsize(final_audio_path)
            print(f"\n🔊 Audio summary successfully created:")
            print(f"   Path: {final_audio_path}")
            print(f"   Size: {file_size:,} bytes")
        else:
            print("\n🔇 Audio summary could not be generated.")
            if generated_audio_path:
                print(f"   - Generated path was: {generated_audio_path}")
                print(f"   - File exists: {os.path.exists(generated_audio_path) if generated_audio_path else False}")
    else:
        print("\n⚠️ No transcripts were generated during the session.")


# --- Function 3: Main Orchestrator ---
async def grade_ant_plus_main(input_questions: list, session_id: str = None, user_id: str = None):
    """
    The main orchestrator function for the GradeAnt+ application.
    Enhanced with better validation and error handling.
    """
    if not input_questions:
        print("No valid questions loaded. Exiting.")
        return
    
    if not session_id:
        session_id = str(uuid.uuid4())
    if not user_id:
        user_id = "student123"
    
    print(f"🚀 INITIALIZING GRADEANT+ SESSION")
    print(f"   Session ID: {session_id}")
    print(f"   User ID: {user_id}")
    print(f"   Questions to process: {len(input_questions)}")
    
    # 1. Initialization
    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from agents import question_pipeline, summary_pipeline

    service = InMemorySessionService()
    #future enhancement: 
    #service = DatabaseSessionService(db_url=f"sqlite:///{DB_FOLDER}/{session_id}.db")

    question_runner = Runner(agent=question_pipeline, session_service=service, app_name="GradeAntPlus")
    summary_runner = Runner(agent=summary_pipeline, session_service=service, app_name="GradeAntPlus")
    
    print("\n--- Starting GradeAnt+ Enhanced Tutoring Session ---")

    # 2. Session Initialization with enhanced metadata
    initial_state = {
        "full_transcript": [],
        "session_start_time": datetime.now().isoformat(),
        "total_questions_planned": len(input_questions),
        "user_id": user_id,
        "session_id": session_id
    }
    
    await service.create_session(
        app_name="GradeAntPlus", 
        user_id=user_id, 
        session_id=session_id, 
        state=initial_state
    )

    # 3. Per-Question Processing with enhanced error handling
    try:
        await process_question_loop(question_runner, service, session_id, user_id, input_questions)
    except Exception as e:
        logger.error(f"Error during question processing: {e}")
        print(f"❌ Error during question processing: {e}")
        return

    # 4. Final Report Generation with enhanced analytics
    try:
        await generate_final_report(summary_runner, service, session_id, user_id)
    except Exception as e:
        logger.error(f"Error during report generation: {e}")
        print(f"❌ Error during report generation: {e}")
        return

    print(f"\n🎓 SESSION COMPLETED SUCCESSFULLY")
    print(f"   All {len(input_questions)} questions processed")
    print(f"   Reports generated and saved to: {OUTPUT_FOLDER}")


# ==============================================================================
# SECTION 6: DRY RUN (no API calls)
# ==============================================================================

DRY_RUN_NOTICE = ("DRY RUN - NOT A REAL SESSION. No model was called; every analysis, "
                  "dialogue and summary in this file is a canned placeholder used to test the pipeline.")


def _mark_markdown_as_dry_run(path: Path) -> None:
    """Tag the study guide's title and add a warning banner under it."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    banner = f"> ⚠️ **{DRY_RUN_NOTICE}**\n\n"
    if text.startswith("# "):
        title, _, rest = text.partition("\n")
        text = f"# [DRY RUN] {title[2:]}\n\n{banner}{rest.lstrip(chr(10))}"
    else:
        text = banner + text
    path.write_text(text, encoding="utf-8")


def _dry_run_knowledge(idx: int) -> dict:
    """Canned KnowledgeAgent output. Odd questions are 'correct' and even ones
    'need feedback', so both routing branches are exercised."""
    correct = idx % 2 == 1
    return {
        "is_correct": correct,
        "needs_feedback": not correct,
        "misconceptions": [] if correct else ["[dry run] placeholder misconception"],
        "missing_steps": [] if correct else ["[dry run] placeholder missing step"],
        "key_concepts": ["[dry run] placeholder concept"],
        "hint": "[dry run] What principle connects the quantities in this problem?",
        "confidence": "dry-run",
    }


async def dry_run_session(input_questions: list, session_id: str, user_id: str):
    """
    Runs the full session flow with canned agent responses instead of LLM calls:
    no API key, network or Google ADK needed. Writes the same JSON log and
    markdown study guide as a live run (no audio), so input loading, routing,
    transcripts and report generation can be checked end to end.
    """
    print("🧪 DRY RUN: no model is called; all agent responses are canned placeholders.")
    logger.info(f"[DRY RUN] Started session {session_id}: no model calls, canned responses")
    print(f"   Session ID: {session_id}")
    print(f"   User ID: {user_id}")
    print(f"   Questions to process: {len(input_questions)}")

    full_transcript = []
    for idx, question_data in enumerate(input_questions, 1):
        knowledge = _dry_run_knowledge(idx)
        if knowledge["needs_feedback"]:
            route = "InteractiveTeachingAgent"
            conversation = [
                {"role": "agent", "content": knowledge["hint"]},
                {"role": "user", "content": "[dry run] simulated student reply"},
            ]
            teaching = "[dry run] placeholder Socratic dialogue summary"
            correct_answer = None
        else:
            route = "CorrectAnswerAgent"
            conversation = []
            teaching = None
            correct_answer = "[dry run] placeholder positive reinforcement"

        print(f"   [{idx}/{len(input_questions)}] {question_data.get('question_id', 'UNKNOWN')} -> {route}")
        full_transcript.append({
            "question_data": question_data,
            "knowledge_response": knowledge,
            "conversation_history": conversation,
            "teaching_response": teaching,
            "correct_answer_response": correct_answer,
            "processing_timestamp": datetime.now().isoformat(),
            "question_index": idx,
        })

    final_summary = {
        "session_overview": "[dry run] placeholder session overview",
        "key_concepts_and_formulas": "[dry run] placeholder concepts and formulas",
        "common_misconceptions_addressed": "[dry run] placeholder misconceptions",
        "areas_for_further_study": "[dry run] placeholder study advice",
    }

    output_report_path = OUTPUT_FOLDER / f"StructuredLog_Session{session_id}.json"
    summary_report_path = OUTPUT_FOLDER / f"SummaryReport_Session{session_id}.md"
    final_report = {
        "dry_run_notice": DRY_RUN_NOTICE,
        "session_metadata": {
            "session_id": session_id,
            "user_id": user_id,
            "total_questions": len(full_transcript),
            "generation_timestamp": datetime.now().isoformat(),
            "ai_model_used": "none (dry run)",
            "dry_run": True,
        },
        "session_summary": final_summary,
        "audio_summary_path": None,
        "detailed_transcript": full_transcript,
    }

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)
    await create_enhanced_markdown_summary(final_summary, full_transcript, summary_report_path)
    _mark_markdown_as_dry_run(summary_report_path)

    print(f"\n💾 Session log:  {output_report_path}")
    print(f"📝 Study guide:  {summary_report_path}")
    print("🔇 Audio: skipped in dry run")
    logger.info(f"[DRY RUN] Completed session {session_id}: {len(full_transcript)} questions")


# ==============================================================================
# SECTION 7: MAIN APPLICATION
# ==============================================================================
async def main():
    parser = argparse.ArgumentParser(description="Run a GradeAnt+ tutoring session.")
    parser.add_argument("--dry-run", action="store_true",
                        help="no API calls: run the session with canned agent responses")
    args = parser.parse_args()

    qa_file_path = INPUT_FOLDER / "Student_C_HW3_with_QP.json"
    qa_file_path = INPUT_FOLDER / "qa.json"
    
    # Enhanced session ID with better formatting
    session_id = datetime_uuid(qa_file_path.name.split('.')[0])
    if args.dry_run:
        session_id += "_dryrun"
    user_id = "student_A"
    
    print(f"🔍 Loading questions from: {qa_file_path}")
    
    # Use enhanced validation function
    input_questions = load_and_validate_questions(qa_file_path)
    if input_questions and args.dry_run:
        await dry_run_session(input_questions, session_id=session_id, user_id=user_id)
    elif input_questions:
        await grade_ant_plus_main(input_questions, session_id=session_id, user_id=user_id)
        print(f"\n🎉 GradeAnt+ session complete! Check {OUTPUT_FOLDER} for all generated files.")
    else:
        print(f"\n❌ No valid questions found in {qa_file_path}")
        print("Please check the file format and ensure it contains valid question objects.")


# ==============================================================================
if __name__ == "__main__":
    os.system('clear')
    asyncio.run(main())