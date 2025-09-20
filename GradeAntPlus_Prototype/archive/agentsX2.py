# ==============================================================================
# SECTION 1: IMPROVED ORCHESTRATOR USING LLM + AGENTTOOLS
# ==============================================================================

import os
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent, BaseAgent
from google.adk.tools import FunctionTool, AgentTool
from google.adk.tools.tool_context import ToolContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from typing import List, AsyncGenerator

from textwrap import dedent
from pathlib import Path
from gtts import gTTS

from prompts import (
    KNOWLEDGE_AGENT_INSTRUCTION, 
    CORRECT_ANSWER_INSTRUCTION, 
    INTERACTIVE_TEACHING_INSTRUCTION,
    SUMMARIZATION_AGENT_INSTRUCTION,
    AUDIO_SCRIPT_AGENT_INSTRUCTION
)

from utils import get_logger
logger = get_logger(__name__)

MODEL = "gemini-2.0-flash"
if os.getenv("GEMINI_MST_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_MST_KEY")
    print("Using GEMINI_MST_KEY for authentication.")
    del os.environ["GEMINI_MST_KEY"]

output_dir = Path(__file__).parent.parent / "data" / "output"
output_dir.mkdir(parents=True, exist_ok=True)
# ==============================================================================
# SECTION 2: PYDANTIC SCHEMAS
# ==============================================================================

class KnowledgeResponse(BaseModel):
    is_correct: bool = Field(description="True if the student's answer is fundamentally correct.")
    needs_feedback: bool = Field(description="True if the student could benefit from guided feedback.")
    misconceptions: List[str] = Field(description="A list of specific conceptual errors.")
    missing_steps: List[str] = Field(description="A list of important logical or calculation steps omitted.")
    key_concepts: List[str] = Field(description="A list of the core physics concepts for the question.")
    hint: str = Field(description="A gentle Socratic question to guide the student.")
    confidence: str = Field(description="Confidence in the evaluation: 'high', 'medium', or 'low'.")

class SummaryResponse(BaseModel):
    session_overview: str = Field(description="A brief summary of the topics covered and student performance.")
    key_concepts_and_formulas: str = Field(description="A list of the most important concepts and formulas from the session.")
    common_misconceptions_addressed: str = Field(description="A summary of recurring errors or misconceptions.")
    areas_for_further_study: str = Field(description="Actionable advice for what the student should study next.")

class AudioScriptResponse(BaseModel):
    script: str = Field(description="The complete, conversational script for the audio summary.")

# ==============================================================================
# SECTION 3: TOOLS
# ==============================================================================
# --- Human Interaction Tool ---
def human_interaction_tool(tool_context: ToolContext, prompt: str) -> dict:
    """Pauses execution, displays a prompt to the human, and waits for their text input."""
    
    # --- REFACTORED: Read turn information from the state ---
    history = tool_context.state.get("conversation_history", [])
    curr_turn = len(history) // 2 + 1
    total_exchanges = len(history) // 2

    print("\n💬 CONVERSATION STATE:")
    print(f"  Current turn: {curr_turn}/3")
    print(f"  Total exchanges so far: {total_exchanges}")

    # Present the agent's question to the user
    print(f"\n🤖 GradeAnt+ Tutor: {prompt}")
    human_input = input("Your response: ").strip()
    
    logger.info(f"HumanTool: Received input: '{human_input}'")
    
    # Allow the user to exit the loop early
    if human_input.lower() in ['exit', 'skip', 'quit']:
        logger.info("HumanTool: User indicated conversation is complete. Escalating to exit loop.")
        print("📚 User requested to end conversation.")
        #tool_context.actions.escalate = True
        return {"human_response": human_input, "status": "completed", "completed_turns": curr_turn+1}

    # Update conversation history in the session state
    history.append({"role": "agent", "content": prompt})
    history.append({"role": "user", "content": human_input})
    tool_context.state["conversation_history"] = history
    
    print(f"📝 Updated conversation history (now {len(history)} entries)")
    status = "completed" if curr_turn >= 3 else "continue"
    return {"human_response": human_input, "status": status, "completed_turns": curr_turn+1}

# --- Exit Loop Tool ---
def exit_loop_tool(tool_context: ToolContext, reason: str) -> dict:
    """Allows the TeachingAgent to programmatically exit the conversation loop."""
    logger.info(f"ExitTool: Agent requested loop exit. Reason: {reason}")
    tool_context.actions.escalate = True
    return {"status": "exited_by_agent", "reason": reason}

# --- Text-to-Speech Tool ---
def text_to_speech_tool(tool_context: ToolContext, script_text: str) -> dict:
    """Converts a given text script into an MP3 audio file and saves it."""
    logger.info("TTS Tool: Starting audio conversion.")
    try:
        # Check if a target audio path is set in the session state
        target_audio_path = tool_context.state.get("target_audio_path")
        
        if target_audio_path:
            # Use the predefined path from main.py
            output_path = Path(target_audio_path)
            logger.info(f"TTS Tool: Using target path: {output_path}")
        else:
            # Fallback to default path (for backward compatibility)
            output_path = output_dir / f"audio_summary.mp3"
            logger.info(f"TTS Tool: Using fallback path: {output_path}")
        
        # Ensure the directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create the gTTS object and save the file
        tts = gTTS(text=script_text, lang='en', slow=False)
        tts.save(str(output_path))
        
        logger.info(f"TTS Tool: Audio file saved successfully to {output_path}")
        
        # Verify file was created and has content
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"TTS Tool: Audio file verified - size: {output_path.stat().st_size} bytes")
            return {"audio_file_path": str(output_path)}
        else:
            logger.error("TTS Tool: Audio file was not created or is empty")
            return {"audio_file_path": None, "error": "Audio file creation failed"}
            
    except Exception as e:
        logger.error(f"TTS Tool: Failed to generate audio file. Error: {e}")
        return {"audio_file_path": None, "error": str(e)}


# A non-llm agent for inserting the turn number into the session state
class TurnCounterAgent(BaseAgent):
    """A simple agent that calculates and injects the current turn number into the state."""
    def __init__(self, max_turns: int):
        super().__init__(name="TurnCounterAgent")
        self._max_turns = max_turns

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        # 1. READS the conversation history from the session state
        history = context.session.state.get("conversation_history", [])
        
        # 2. CALCULATES the current turn number
        current_turn = (len(history) // 2) + 1

        # 3. WRITES the turn info back into the session state
        context.session.state["current_turn"] = current_turn
        context.session.state["max_turns"] = self._max_turns

        logger.info(f"TurnCounterAgent: It is now Turn {current_turn}/{self._max_turns}.")
        yield Event(author=self.name)

###############################################################################################
# --- Tools the agent can use ---
human_tool = FunctionTool(func=human_interaction_tool)
exit_tool = FunctionTool(func=exit_loop_tool)
tts_tool = FunctionTool(func=text_to_speech_tool) # NEW: Create the tool instance

# ==============================================================================
# SECTION 4: QUESTION PIPELINE
# ==============================================================================

knowledge_agent = LlmAgent(
    model=MODEL,
    name="KnowledgeAgent",
    description="Analyzes the student's knowledge and provides feedback.",
    instruction=KNOWLEDGE_AGENT_INSTRUCTION,
    output_schema=KnowledgeResponse,
    output_key="knowledge_response",
    disallow_transfer_to_parent=True,  # requires when output_schema is used
    disallow_transfer_to_peers=True,  # requires when output_schema is used
)

interactive_teaching_agent = LlmAgent(
    model=MODEL,
    name="InteractiveTeachingAgent",
    description="Conducts a Socratic dialogue with the student.",
    instruction=INTERACTIVE_TEACHING_INSTRUCTION,
    tools=[human_tool, exit_tool]
)

correct_answer_agent = LlmAgent(
    model=MODEL,
    name="CorrectAnswerAgent",
    description="Prases the student's answer and provides feedback.", 
    instruction=CORRECT_ANSWER_INSTRUCTION,
)

# ==============================================================================
# SECTION 5: LLM ORCHESTRATOR WITH AGENTTOOLS
# ==============================================================================
MAX_TEACHING_TURNS = 3

teaching_loop_agent = LoopAgent(
    name="TeachingLoopAgent",
    description="Conducts a multi-turn Socratic dialogue with the student.",
    sub_agents=[
        TurnCounterAgent(max_turns=MAX_TEACHING_TURNS),
        interactive_teaching_agent,
    ],
    max_iterations=MAX_TEACHING_TURNS,
)

# conditional nodes
teaching_loop_agent_tool = AgentTool(agent=teaching_loop_agent)
correct_answer_agent_tool = AgentTool(agent=correct_answer_agent)

# The main orchestrator - conditional decision maker
question_orchestrator = LlmAgent(
    model=MODEL,
    name="QuestionOrchestrator",
    description="Tutoring system orchestrator.",
    instruction=dedent("""
        You are the orchestrator for an educational tutoring system.
        Delegate the student to the appropriate agent based on the knowledge analysis.

        **CONTEXT:**
        The knowledge analysis is available in the {knowledge_response} variable.

        **SIMPLE ROUTING:**
        - If the analysis indicates 'needs_feedback' is true, you MUST use the `teaching_loop_agent_tool`.
        - If the analysis indicates 'needs_feedback' is false, you MUST use the `correct_answer_agent_tool`.
        - If you cannot determine needs_feedback value, default to teaching_loop_agent_tool for safety.
        
        Trust the boolean value from the knowledge analysis and call the appropriate tool.
        """),
    tools=[teaching_loop_agent_tool, correct_answer_agent_tool]
    )

# Main question processing pipeline: KnowledgeAgent → Orchestrator
question_pipeline = SequentialAgent(
    name="QuestionProcessor",
    description="Question processing pipeline.",
    sub_agents=[
        knowledge_agent, 
        question_orchestrator
    ]
)

# ==============================================================================
# SECTION 6: SUMMARY PIPELINE
# ==============================================================================

summarization_agent = LlmAgent(
    model=MODEL,
    name="SummarizationAgent",
    description="Generates a structured text summary of the session.",
    instruction=SUMMARIZATION_AGENT_INSTRUCTION,
    output_schema=SummaryResponse,
    output_key="final_summary",
    disallow_transfer_to_parent=True,  # requires when output_schema is used
    disallow_transfer_to_peers=True,  # requires when output_schema is used
)

audio_script_agent = LlmAgent(
    model=MODEL,
    name="AudioScriptAgent",
    description="Converts the summary into a conversational audio script.",
    instruction=AUDIO_SCRIPT_AGENT_INSTRUCTION,
    output_schema=AudioScriptResponse,
    output_key="audio_script",
    disallow_transfer_to_parent=True,    # requires when output_schema is used
    disallow_transfer_to_peers=True,    # requires when output_schema is used
)

tts_agent = LlmAgent(
    model=MODEL,
    name="TtsAgent",
    description="Converts the audio script into an MP3 audio file.",
    instruction=dedent("""
        You have been given a script in the {audio_script} variable.
        Use the text_to_speech_tool to convert this script to an audio file.
    """),
    tools=[FunctionTool(func=text_to_speech_tool)],
    output_key="tts_output"
)

summary_pipeline = SequentialAgent(
    name="SummaryOrchestrator",
    description="Summary generation pipeline.",
    sub_agents=[summarization_agent, audio_script_agent, tts_agent]
)