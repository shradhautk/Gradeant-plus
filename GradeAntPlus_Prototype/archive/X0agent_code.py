import uuid
import json
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator

# Import from the prompts.py file
from prompts import StateKeys, PROMPT_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gradeant_plus.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('GradeAntPlus')

# Suppress noisy Google ADK internal logging
logging.getLogger('google_adk').setLevel(logging.WARNING)
logging.getLogger('google.adk').setLevel(logging.WARNING)
logging.getLogger('google_adk.google.adk.models.registry').setLevel(logging.WARNING)
logging.getLogger('google_adk.google.adk.models').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.WARNING)
logging.getLogger('google_genai.models').setLevel(logging.WARNING)


from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext

# ==============================================================================
# SECTION 1: TOOL DEFINITIONS
# ==============================================================================

def exit_loop(tool_context: ToolContext) -> dict:
    """Signals the parent LoopAgent to terminate its execution immediately."""
    logger.info(f"[TOOL] exit_loop triggered by {tool_context.agent_name}")
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    return {}

def provide_hint(tool_context: ToolContext) -> dict:
    """Retrieves a hint from the expert analysis to be shown to the student."""
    logger.info(f"[TOOL] provide_hint called by {tool_context.agent_name}")
    analysis = tool_context.session.state.get(StateKeys.EXPERT_ANALYSIS)
    if isinstance(analysis, dict):
        hint = analysis.get("hint", "No hint available.")
        logger.info(f"[TOOL] Hint provided: {hint[:50]}...")
    else:
        hint = "Hint could not be retrieved at this time."
        logger.warning("[TOOL] Could not retrieve hint from expert analysis")
    return {"hint": hint}

def skip_feedback(tool_context: ToolContext) -> dict:
    """Allows student to skip remaining feedback turns."""
    logger.info("[TOOL] skip_feedback triggered - student requested skip")
    print(f"  [Tool Call] skip_feedback triggered")
    tool_context.actions.escalate = True
    return {"message": "Feedback skipped by student request."}

def human_interaction_tool(tool_context: ToolContext, prompt: str, turn_number: int = 1, max_turns: int = 3) -> dict:
    """Human-in-the-loop interaction tool following ADK pattern."""
    logger.info(f"[HUMAN_TOOL] Starting human interaction - Turn {turn_number}/{max_turns}")
    logger.info(f"[HUMAN_TOOL] Prompt: {prompt[:100]}...")
    
    # Display the prompt to the human
    print(f"\n--- Turn {turn_number}/{max_turns} ---")
    print(f"🤖 GradeAnt+ Tutor: {prompt}")
    print("\nOptions:")
    print("- Ask a follow-up question or request clarification")
    print("- Type 'done' when satisfied")
    print("- Type 'skip' to move to next question") 
    print("- Type 'hint' for additional help")
    
    # Get human input
    while True:
        human_input = input("\nYour response: ").strip()
        
        if not human_input:
            print("Please provide input or use one of the commands (done, skip, hint).")
            continue
        
        logger.info(f"[HUMAN_TOOL] Human input received: {human_input}")
        
        # Process special commands
        if human_input.lower() in ['done', 'satisfied', 'got it', 'understand', 'thanks', 'thx']:
            logger.info("[HUMAN_TOOL] Human indicated satisfaction")
            tool_context.actions.escalate = True  # End the loop
            return {
                "human_response": human_input,
                "action": "satisfied",
                "continue_interaction": False
            }
            
        elif human_input.lower() == 'skip':
            logger.info("[HUMAN_TOOL] Human requested skip")
            tool_context.actions.escalate = True  # End the loop
            return {
                "human_response": human_input,
                "action": "skip",
                "continue_interaction": False
            }
            
        elif human_input.lower() == 'hint':
            # Get hint from expert analysis
            analysis = tool_context.session.state.get(StateKeys.EXPERT_ANALYSIS)
            if isinstance(analysis, dict):
                hint = analysis.get("hint", "No specific hint available.")
                print(f"💡 Hint: {hint}")
                logger.info(f"[HUMAN_TOOL] Hint provided: {hint}")
                continue  # Ask for input again
            else:
                print("💡 No hint available at this time.")
                continue
                
        else:
            # Regular interaction - return the input for processing
            logger.info(f"[HUMAN_TOOL] Processing regular interaction: {human_input[:50]}...")
            
            # Update conversation history
            current_history = tool_context.session.state.get(StateKeys.CONVERSATION_HISTORY, [])
            current_history.append({"role": "user", "content": human_input})
            tool_context.session.state[StateKeys.CONVERSATION_HISTORY] = current_history
            
            # Check if max turns reached
            continue_interaction = turn_number < max_turns
            if not continue_interaction:
                logger.info("[HUMAN_TOOL] Maximum turns reached")
                print(f"\n🤖 GradeAnt+: We've completed {max_turns} feedback turns. Moving to the next question.")
            
            return {
                "human_response": human_input,
                "action": "continue",
                "continue_interaction": continue_interaction,
                "turn_number": turn_number
            }

exit_loop_tool = FunctionTool(func=exit_loop)
provide_hint_tool = FunctionTool(func=provide_hint)
skip_feedback_tool = FunctionTool(func=skip_feedback)
human_interaction_tool_func = FunctionTool(func=human_interaction_tool)

# ==============================================================================
# SECTION 2: AGENT DEFINITIONS
# ==============================================================================

knowledge_agent = LlmAgent(
    model="gemini-2.5-flash", 
    name="KnowledgeAgent", 
    instruction=PROMPT_CONFIG["knowledge_agent"], 
    output_key=StateKeys.EXPERT_ANALYSIS
)

lesson_planner_agent = LlmAgent(
    model="gemini-2.5-flash", 
    name="LessonPlannerAgent", 
    instruction=PROMPT_CONFIG["lesson_planner"], 
    output_key=StateKeys.LESSON_PLAN
)

teaching_agent = LlmAgent(
    model="gemini-2.5-flash", 
    name="TeachingAgent", 
    instruction=PROMPT_CONFIG["teaching_agent"], 
    tools=[exit_loop_tool, provide_hint_tool, skip_feedback_tool, human_interaction_tool_func]
)

correct_answer_agent = LlmAgent(
    model="gemini-2.5-flash", 
    name="CorrectAnswerAgent", 
    instruction=PROMPT_CONFIG["correct_answer_agent"]
)

summarization_agent = LlmAgent(
    model="gemini-2.5-flash", 
    name="SummarizationAgent", 
    instruction=PROMPT_CONFIG["summarization_agent"], 
    output_key=StateKeys.TEXT_SUMMARY
)

# NEW: Audio Summary Agent for TTS
audio_summary_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="AudioSummaryAgent", 
    instruction=PROMPT_CONFIG.get("audio_summary_agent", "Create a podcast-style script for audio summary"),
    output_key=StateKeys.AUDIO_SCRIPT
)

class FeedbackTriageAgent(BaseAgent):
    """Enhanced triage agent that determines if feedback is needed and what type."""
    def __init__(self):
        super().__init__(name="FeedbackTriageAgent")

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info("[AGENT] FeedbackTriageAgent starting analysis")
        expert_analysis_str = context.session.state.get(StateKeys.EXPERT_ANALYSIS)
        analysis_dict = {}
        
        if expert_analysis_str and isinstance(expert_analysis_str, str):
            try:
                analysis_dict = json.loads(expert_analysis_str)
                context.session.state[StateKeys.EXPERT_ANALYSIS] = analysis_dict
                logger.info(f"[AGENT] Expert analysis parsed successfully: is_correct={analysis_dict.get('is_correct')}")
            except json.JSONDecodeError:
                logger.error(f"[AGENT] Could not parse expert_analysis JSON: {expert_analysis_str}")
                print(f"  [Warning] Could not parse expert_analysis JSON: {expert_analysis_str}")
                analysis_dict = {"is_correct": False, "needs_feedback": True}

        # Enhanced feedback decision logic per requirements
        is_correct = analysis_dict.get("is_correct", False)
        has_misconceptions = bool(analysis_dict.get("misconceptions", []))
        missing_steps = bool(analysis_dict.get("missing_steps", []))
        needs_feedback = analysis_dict.get("needs_feedback", not is_correct)
        
        # Decision logic: feedback needed if incorrect OR has misconceptions OR missing key steps
        if needs_feedback or has_misconceptions or missing_steps:
            status = "needs_feedback"
        elif is_correct:
            status = "correct"
        else:
            status = "unclear"  # Edge case
            
        context.session.state[StateKeys.FEEDBACK_STATUS] = status
        context.session.state[StateKeys.NEEDS_FEEDBACK] = needs_feedback
        
        logger.info(f"[AGENT] Feedback triage complete - Status: {status}, Needs feedback: {needs_feedback}")
        logger.info(f"[AGENT] Misconceptions found: {len(analysis_dict.get('misconceptions', []))}")
        logger.info(f"[AGENT] Missing steps: {len(analysis_dict.get('missing_steps', []))}")
        
        yield Event(author=self.name)

class GatekeeperAgent(BaseAgent):
    """Acts as an 'if' condition for a LoopAgent branch."""
    def __init__(self, name: str, state_key_to_check: str, required_value: str):
        super().__init__(name=name)
        self._key = state_key_to_check
        self._value = required_value

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        if context.session.state.get(self._key) == self._value:
            yield Event(author=self.name)
        else:
            yield Event(author=self.name, actions=EventActions(escalate=True))

# ==============================================================================
# SECTION 3: ORCHESTRATOR DEFINITIONS  
# ==============================================================================

teaching_loop = LoopAgent(
    name="TeachingLoop", 
    sub_agents=[teaching_agent], 
    max_iterations=3
)

feedback_branch = SequentialAgent(
    name="FeedbackBranch", 
    sub_agents=[lesson_planner_agent, teaching_loop]
)

conditional_feedback_branch = LoopAgent(
    name="ConditionalFeedbackBranch", 
    sub_agents=[
        GatekeeperAgent(
            name="FeedbackGatekeeper", 
            state_key_to_check=StateKeys.FEEDBACK_STATUS, 
            required_value="needs_feedback"), 
        feedback_branch
    ], 
    max_iterations=1
)
conditional_praise_branch = LoopAgent(
    name="ConditionalPraiseBranch", 
    sub_agents=[
        GatekeeperAgent(
            name="PraiseGatekeeper", 
            state_key_to_check=StateKeys.FEEDBACK_STATUS, 
            required_value="correct"), 
        correct_answer_agent
    ], 
    max_iterations=1
)

question_processor = SequentialAgent(
    name="QuestionProcessor", 
    sub_agents=[knowledge_agent, FeedbackTriageAgent(), conditional_feedback_branch, conditional_praise_branch]
)

# Enhanced summary pipeline with audio support
summary_pipeline = SequentialAgent(
    name="SummaryPipeline", 
    sub_agents=[summarization_agent, audio_summary_agent]
)

# ==============================================================================
# SECTION 4: HELPER FUNCTIONS
# ==============================================================================

def parse_latex_ascii(text: str) -> str:
    """Basic LaTeX/ASCII to text conversion for model processing."""
    # This is a simplified parser - you'd want more robust parsing
    replacements = {
        r'\frac{': '(',
        r'}{': ')÷(',
        r'}': ')',
        r'\cdot': '×',
        r'\times': '×',
        r'\div': '÷',
        r'\sqrt{': '√(',
        r'^2': '²',
        r'^3': '³',
        r'\pi': 'π',
        r'\theta': 'θ',
        r'\omega': 'ω',
        r'\alpha': 'α',
        r'\beta': 'β',
        r'\gamma': 'γ'
    }
    
    result = text
    for latex, replacement in replacements.items():
        result = result.replace(latex, replacement)
    
    return result

def validate_question_format(question_data: dict) -> bool:
    """Validates question data matches expected format from requirements."""
    required_fields = ["question_id", "question_text", "student_answer", "reference_answer"]
    return all(field in question_data for field in required_fields)

# ==============================================================================
# SECTION 5: MAIN APPLICATION LOGIC
# ==============================================================================

def load_questions_from_file(filename: str) -> list:
    """Loads the list of questions from a JSON file."""
    logger.info(f"[SYSTEM] Loading questions from file: {filename}")
    try:
        with open(filename, 'r') as f:
            questions = json.load(f)
            
        logger.info(f"[SYSTEM] Found {len(questions)} questions in file")
            
        # Validate format
        valid_questions = []
        for i, q in enumerate(questions):
            if validate_question_format(q):
                # Parse LaTeX/ASCII in answers and question
                q["question_text_parsed"] = parse_latex_ascii(q["question_text"])
                q["student_answer_parsed"] = parse_latex_ascii(q["student_answer"])
                q["reference_answer_parsed"] = parse_latex_ascii(q["reference_answer"])
                valid_questions.append(q)
                logger.info(f"[SYSTEM] Question {i+1} ({q['question_id']}) validated and parsed")
            else:
                logger.error(f"[SYSTEM] Invalid question format at index {i}: {q}")
                print(f"[Warning] Invalid question format: {q}")
                
        logger.info(f"[SYSTEM] Successfully loaded {len(valid_questions)} valid questions")
        return valid_questions
        
    except FileNotFoundError:
        logger.error(f"[SYSTEM] File not found: {filename}")
        print(f"[Error] The file '{filename}' was not found.")
        return []
    except json.JSONDecodeError:
        logger.error(f"[SYSTEM] Invalid JSON format in file: {filename}")
        print(f"[Error] The file '{filename}' is not a valid JSON file.")
        return []

async def generate_audio_summary(session_service, user_id: str, session_id: str):
    """Placeholder for TTS integration - generates audio from text summary."""
    logger.info("[AUDIO] Starting audio summary generation")
    session = await session_service.get_session("GradeAntPlus", user_id, session_id)
    audio_script = session.state.get(StateKeys.AUDIO_SCRIPT, "")
    
    if not audio_script:
        logger.warning("[AUDIO] No audio script found in session state")
        return
    
    # TODO: Integrate with TTS service (e.g., Google Text-to-Speech, ElevenLabs, etc.)
    logger.info("[AUDIO] Audio script ready for TTS conversion")
    print("\n--- AUDIO SUMMARY SCRIPT (Ready for TTS) ---")
    print(audio_script)
    print("\n--- End Audio Script ---")
    
    # For now, just save the script to a file
    filename = f"audio_script_{session_id}.txt"
    try:
        with open(filename, "w") as f:
            f.write(audio_script)
        logger.info(f"[AUDIO] Audio script saved to {filename}")
        print(f"Audio script saved to {filename}")
    except Exception as e:
        logger.error(f"[AUDIO] Failed to save audio script: {e}")

async def grade_ant_plus_main():
    """Main function to run the GradeAnt+ orchestration."""
    logger.info("="*60)
    logger.info("[SYSTEM] Starting GradeAnt+ Physics Tutor Session")
    logger.info("="*60)
    
    service = InMemorySessionService()
    question_runner = Runner(agent=question_processor, session_service=service, app_name="GradeAntPlus")
    summary_runner = Runner(agent=summary_pipeline, session_service=service, app_name="GradeAntPlus")

    input_questions = load_questions_from_file("qa.json")
    if not input_questions:
        logger.error("[SYSTEM] No valid questions to process - exiting")
        print("No valid questions to process. Exiting.")
        return

    session_id, user_id = str(uuid.uuid4()), "student123"
    logger.info(f"[SESSION] Created session - ID: {session_id}, User: {user_id}")
    
    await service.create_session(
        app_name="GradeAntPlus", 
        user_id=user_id, 
        session_id=session_id,
        state={StateKeys.FULL_TRANSCRIPT: [], StateKeys.SESSION_METADATA: {"total_questions": len(input_questions), "start_time": datetime.now().isoformat()}}
    )
    
    print("--- Welcome to GradeAnt+ Physics Tutor ---")
    print(f"Processing {len(input_questions)} questions...")
    logger.info(f"[SESSION] Processing {len(input_questions)} questions")

    for i, question_data in enumerate(input_questions, 1):
        logger.info(f"[QUESTION] Starting question {i}/{len(input_questions)}: {question_data['question_id']}")
        print(f"\n{'='*20} Question {i}/{len(input_questions)}: {question_data['question_id']} {'='*20}")
        
        # Prepare session state with all required data
        session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        session.state.update({
            StateKeys.CURRENT_QUESTION: question_data,
            StateKeys.QUESTION_TEXT: question_data["question_text_parsed"],
            StateKeys.STUDENT_ANSWER: question_data["student_answer_parsed"],
            StateKeys.REFERENCE_ANSWER: question_data["reference_answer_parsed"],
            StateKeys.CONVERSATION_HISTORY: [{"role": "user", "content": question_data["student_answer"]}],
            StateKeys.QUESTION_ID: question_data["question_id"]
        })
        
        logger.info(f"[QUESTION] Session state updated with question data")
        await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)
        
        current_msg = types.Content(role="user", parts=[types.Part(text=question_data["student_answer"])])

        # Initial processing - Knowledge Agent analysis and feedback decision
        logger.info("[PROCESSING] Starting initial analysis by Knowledge Agent")
        print("🤖 Analyzing your answer...")
        async for ev in question_runner.run_async(user_id=user_id, session_id=session_id, new_message=current_msg):
            logger.debug(f"[AGENT] Event from: {ev.author}")
            print(f"-> Agent: {ev.author}")
            if ev.is_final_response() and ev.content and ev.content.parts:
                initial_response = ev.content.parts[0].text
                logger.info(f"[AGENT] Final response from {ev.author}:\n{initial_response}...")
                print(f"🤖 GradeAnt+: {initial_response}")

        # Check if interactive feedback is needed
        session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        feedback_status = session.state.get(StateKeys.FEEDBACK_STATUS)
        logger.info(f"[DECISION] Feedback status determined: {feedback_status}")
        
        if feedback_status == "needs_feedback":
            logger.info("[INTERACTION] Starting interactive feedback session using Human-in-the-Loop pattern")
            print(f"\n{'='*15} Interactive Feedback Session - Up to 3 turns {'='*15}")
            print("The teaching agent will guide you through interactive feedback.")
            print("You can engage naturally - the system will handle the conversation flow.\n")
            
            # Initialize conversation turn tracking
            session.state[StateKeys.CURRENT_TURN] = 1
            session.state[StateKeys.MAX_TURNS] = 3
            await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=session.state)
            
            # Start the teaching loop - it will use the human_interaction_tool
            teaching_msg = types.Content(role="user", parts=[types.Part(text="Start interactive teaching session")])
            
            async for ev in question_runner.run_async(user_id=user_id, session_id=session_id, new_message=teaching_msg):
                if ev.is_final_response() and ev.content and ev.content.parts:
                    final_response = ev.content.parts[0].text
                    logger.info(f"[INTERACTION] Teaching session concluded:\n{final_response}...")
                    print(f"🤖 GradeAnt+: {final_response}")
                    break
                    
        elif feedback_status == "correct":
            logger.info("[DECISION] Answer was correct - no feedback needed")
            print("🤖 GradeAnt+: Your answer was correct! No additional feedback needed.")
        else:
            logger.info(f"[DECISION] Unknown feedback status: {feedback_status}")
            print("🤖 GradeAnt+: Analysis complete for this question.")

        # Store question transcript
        final_session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
        question_transcript = {
            "question_data": question_data,
            "expert_analysis": final_session.state.get(StateKeys.EXPERT_ANALYSIS),
            "conversation_history": final_session.state.get(StateKeys.CONVERSATION_HISTORY),
            "feedback_provided": final_session.state.get(StateKeys.FEEDBACK_STATUS) == "needs_feedback",
            "total_turns": final_session.state.get(StateKeys.CURRENT_TURN, 1) - 1
        }
        
        final_session.state[StateKeys.FULL_TRANSCRIPT].append(question_transcript)
        await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=final_session.state)
        logger.info(f"[QUESTION] Question {question_data['question_id']} processing complete - transcript saved")

    logger.info("[SUMMARY] All questions processed - generating final summary")
    print(f"\n{'='*20} All questions complete. Generating revision summary... {'='*20}")
    
    # Generate comprehensive summary
    summary_msg = types.Content(role="user", parts=[types.Part(text="Generate comprehensive revision summary with audio script.")])
    async for ev in summary_runner.run_async(user_id=user_id, session_id=session_id, new_message=summary_msg):
        if ev.is_final_response() and ev.content and ev.content.parts:
            logger.info(f"[SUMMARY] Summary generated by {ev.author}")
            print(f"🤖 GradeAnt+: {ev.content.parts[0].text}")

    # Generate audio summary
    await generate_audio_summary(service, user_id, session_id)

    final_session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
    final_session.state[StateKeys.SESSION_METADATA]["end_time"] = datetime.now().isoformat()
    
    print("\n--- Final Text Summary ---")
    print(final_session.state.get(StateKeys.TEXT_SUMMARY, "No summary was generated."))
    print(f"\n--- Session Complete! Processed {len(input_questions)} questions ---")
    
    logger.info(f"[SESSION] Session complete - processed {len(input_questions)} questions")
    logger.info("="*60)
    logger.info(final_session.state.get(StateKeys.CONVERSATION_HISTORY))
    logger.info("="*60)
    
    final_session.state[StateKeys.FULL_TRANSCRIPT].append({"question_data": None, "expert_analysis": None, "conversation_history": final_session.state.get(StateKeys.CONVERSATION_HISTORY), "feedback_provided": False, "total_turns": final_session.state.get(StateKeys.CURRENT_TURN, 1) - 1})
    await service.create_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id, state=final_session.state)

    print(f"\n{'='*20} All questions complete. Generating revision summary... {'='*20}")
    
    # Generate comprehensive summary
    summary_msg = types.Content(role="user", parts=[types.Part(text="Generate comprehensive revision summary with audio script.")])
    async for ev in summary_runner.run_async(user_id=user_id, session_id=session_id, new_message=summary_msg):
        if ev.is_final_response() and ev.content and ev.content.parts:
            print(f"🤖 GradeAnt+: {ev.content.parts[0].text}")

    # Generate audio summary
    await generate_audio_summary(service, user_id, session_id)

    final_session = await service.get_session(app_name="GradeAntPlus", user_id=user_id, session_id=session_id)
    print("\n--- Final Text Summary ---")
    print(final_session.state.get(StateKeys.TEXT_SUMMARY, "No summary was generated."))
    print(f"\n--- Session Complete! Processed {len(input_questions)} questions ---")


if __name__ == "__main__":
    print("Starting GradeAnt+ Physics Tutor...")
    asyncio.run(grade_ant_plus_main())
    print("\nGradeAnt+ session finished.")