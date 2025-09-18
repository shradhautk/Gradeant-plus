# ==============================================================================
# SECTION 0: IMPORTS
# ==============================================================================

import os
from typing import List, AsyncGenerator
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext

from pathlib import Path  # NEW: Import Path for file operations
from gtts import gTTS    # NEW: Import the gTTS library

from prompts import (
    KNOWLEDGE_AGENT_INSTRUCTION, 
    CORRECT_ANSWER_INSTRUCTION, 
    TEACHING_AGENT_INSTRUCTION,
    SUMMARIZATION_AGENT_INSTRUCTION,
    AUDIO_SCRIPT_AGENT_INSTRUCTION
)

from utils import get_logger
logger = get_logger(__name__)

MODEL = "gemini-2.0-flash"
if os.getenv("GEMINI_MST_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_MST_KEY")
    print("Using GEMINI_MST_KEY for authentication.")
    del os.environ["GEMINI_API_KEY"]

output_dir = Path(__file__).parent.parent / "data" / "output"
output_dir.mkdir(parents=True, exist_ok=True)
# ==============================================================================
# SECTION 1: PYDANTIC OUTPUT SCHEMA
# ==============================================================================

# --- Pydantic schema for the knowledge agent ---
class KnowledgeResponse(BaseModel):
    is_correct: bool = Field(description="True if the student's answer is fundamentally correct.")
    needs_feedback: bool = Field(description="True if the student could benefit from guided feedback.")
    misconceptions: List[str] = Field(description="A list of specific conceptual errors.")
    missing_steps: List[str] = Field(description="A list of important logical or calculation steps omitted.")
    key_concepts: List[str] = Field(description="A list of the core physics concepts for the question.")
    hint: str = Field(description="A gentle Socratic question to guide the student.")
    confidence: str = Field(description="Confidence in the evaluation: 'high', 'medium', or 'low'.")

# --- Pydantic schema for the summary ---
class SummaryResponse(BaseModel):
    """Defines the structured output for the SummarizationAgent."""
    session_overview: str = Field(description="A brief summary of the topics covered and student performance.")
    key_concepts_and_formulas: str = Field(description="A list of the most important concepts and formulas from the session.")
    common_misconceptions_addressed: str = Field(description="A summary of recurring errors or misconceptions.")
    areas_for_further_study: str = Field(description="Actionable advice for what the student should study next.")

# --- Pydantic schema for the audio script ---
class AudioScriptResponse(BaseModel):
    """Defines the structured output for the AudioScriptAgent."""
    script: str = Field(description="The complete, conversational script for the audio summary.")

# ==============================================================================
# SECTION 2: HUMAN-IN-THE-LOOP TOOLS
# ==============================================================================

# --- Human Interaction Tool ---
def human_interaction_tool(tool_context: ToolContext, prompt: str) -> dict:
    """Pauses execution, displays a prompt to the human, and waits for their text input."""
    logger.info(f"HumanTool: Prompting user: '{prompt}")
    
    # Print current conversation state
    print("\n💬 CONVERSATION STATE:")
    history = tool_context.state.get("conversation_history", [])
    print(f"  Current turn: {len(history) // 2 + 1}")
    print(f"  Total exchanges so far: {len(history) // 2}")
    
    # Present the agent's question to the user
    print(f"\n🤖 GradeAnt+ Tutor: {prompt}")
    human_input = input("Your response: ").strip()
    
    logger.info(f"HumanTool: Received input: '{human_input}'")
    
    # Allow the user to exit the loop early
    if human_input.lower() in ['done', 'exit', 'got it', 'thanks', 'skip']:
        logger.info("HumanTool: User indicated conversation is complete. Escalating to exit loop.")
        print("🔚 User requested to end conversation.")
        tool_context.escalate = True  # This signals the parent LoopAgent to stop
        return {"human_response": human_input, "status": "completed"}

    # Update conversation history in the session state
    history.append({"role": "agent", "content": prompt})
    history.append({"role": "user", "content": human_input})
    tool_context.state["conversation_history"] = history
    
    print(f"📝 Updated conversation history (now {len(history)} entries)")
    
    return {"human_response": human_input}

# --- Exit Loop Tool ---
def exit_loop_tool(tool_context: ToolContext, reason: str) -> dict:
    """Allows the TeachingAgent to programmatically exit the conversation loop."""
    logger.info(f"ExitTool: Agent requested loop exit. Reason: {reason}")
    tool_context.actions.escalate = True  # Signal the parent LoopAgent to stop
    return {"status": "exited_by_agent", "reason": reason}

# --- Text-to-Speech Tool ---
def text_to_speech_tool(tool_context: ToolContext, script_text: str) -> dict:
    """Converts a given text script into an MP3 audio file and saves it."""
    logger.info("TTS Tool: Starting audio conversion.")
    try:
        # Use the session ID to create a unique filename
        output_path = output_dir / f"audio_summary.mp3"

        # Create the gTTS object and save the file
        tts = gTTS(text=script_text, lang='en', slow=False)
        tts.save(str(output_path))
        
        logger.info(f"TTS Tool: Audio file saved successfully to {output_path}")
        # Return the path to be stored in the session state
        return {"audio_file_path": str(output_path)}
    except Exception as e:
        logger.error(f"TTS Tool: Failed to generate audio file. Error: {e}")
        return {"audio_file_path": None, "error": str(e)}


# --- Tools the agent can use ---
human_tool = FunctionTool(func=human_interaction_tool)
exit_tool = FunctionTool(func=exit_loop_tool)
tts_tool = FunctionTool(func=text_to_speech_tool) # NEW: Create the tool instance

# ==============================================================================
# SECTION 3: AGENT DEFINITIONS (TeachingAgent is updated)
# ==============================================================================

# --- Agent 1: Knowledge Agent ---
knowledge_agent = LlmAgent(
    model=MODEL,  # Updated to a valid model name
    name="KnowledgeAgent",
    instruction=KNOWLEDGE_AGENT_INSTRUCTION,
    output_schema=KnowledgeResponse,
    output_key="knowledge_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True
)

# --- Agent 2: Correct Answer Agent ---
correct_answer_agent = LlmAgent(
    model=MODEL,  # Updated to a valid model name
    name="CorrectAnswerAgent",
    instruction=CORRECT_ANSWER_INSTRUCTION,
)

# --- Agent 3: Teaching Agent ---
teaching_agent = LlmAgent(
    model=MODEL,  # Updated to a valid model name
    name="TeachingAgent",
    instruction=TEACHING_AGENT_INSTRUCTION,
    tools=[human_tool, exit_tool]  # Agent now has access to the new tools
)

# --- Agent 4: Summarization Agent ---
summarization_agent = LlmAgent(
    model=MODEL,
    name="SummarizationAgent",
    instruction=SUMMARIZATION_AGENT_INSTRUCTION,
    output_schema=SummaryResponse,
    output_key="final_summary",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True
)


# --- Agent 5: Audio Script Agent ---
audio_script_agent = LlmAgent(
    model=MODEL,
    name="AudioScriptAgent",
    instruction=AUDIO_SCRIPT_AGENT_INSTRUCTION,
    output_schema=AudioScriptResponse,
    output_key="audio_script",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True
)

# --- Agent 6: TTS Agent (calls the tool) ---
tts_agent = LlmAgent(
    model=MODEL,
    name="TtsAgent",
    instruction="You have been given a script in the {audio_script} variable. Use the text_to_speech_tool to convert this script to an audio file.",
    tools=[tts_tool],
    output_key="tts_output"
)

# ==============================================================================
# SECTION 4: CUSTOM AGENTS FOR ORCHESTRATION
# ==============================================================================
# --- Agent 7: Feedback Triage Agent ---
class FeedbackTriageAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="FeedbackTriageAgent")
    
    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info("TriageAgent: Analyzing knowledge response.")
        
        # Print all input data keys
        # print("\n📋 INPUT DATA:")
        # input_keys = ["question_id", "student_answer", "reference_answer", "question_text"]
        # for key in input_keys:
        #     value = context.session.state.get(key, "NOT FOUND")
        #     print(f"  {key}: {value}")
        
        # Get and display knowledge response
        knowledge_dict = context.session.state.get("knowledge_response")
        print("\n🧠 KNOWLEDGE ANALYSIS:")
        if isinstance(knowledge_dict, dict):
            schema_keys = ["is_correct", "needs_feedback", "misconceptions", "missing_steps", 
                          "key_concepts", "hint", "confidence"]
            for key in schema_keys:
                value = knowledge_dict.get(key, "NOT FOUND")
                print(f"  {key}: {value}")
        else:
            print("  ERROR: Knowledge response is not a dictionary")
        
        status = "needs_feedback"
        if isinstance(knowledge_dict, dict) and knowledge_dict.get("is_correct", False):
            status = "correct"
        
        context.session.state["feedback_status"] = status
        logger.info(f"TriageAgent: Feedback status set to '{status}'.")
        print(f"\n✅ FEEDBACK STATUS: {status}\n")
        yield Event(author=self.name)

# --- Agent 8: Gatekeeper Agent ---
class GatekeeperAgent(BaseAgent):
    def __init__(self, name: str, state_key_to_check: str, required_value: str):
        super().__init__(name=name)
        self._key = state_key_to_check
        self._value = required_value
    
    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        current_value = context.session.state.get(self._key)
        if current_value == self._value:
            yield Event(author=self.name)
        else:
            yield Event(author=self.name, actions=EventActions(escalate=True))

# ==============================================================================
# SECTION 5: ORCHESTRATOR DEFINITION (Updated)
# ==============================================================================

# This is dedicated loop for the 3-turn teaching conversation.
teaching_loop = LoopAgent(
    name="TeachingLoop",
    sub_agents=[teaching_agent],
    max_iterations=3  # The conversation will last at most 3 turns
)

# This is praise branch, runs only if the feedback status is correct.
conditional_praise_branch = LoopAgent(
    name="ConditionalPraiseBranch",
    sub_agents=[
        GatekeeperAgent(
            name="PraiseGatekeeper", 
            state_key_to_check="feedback_status", 
            required_value="correct"
        ), 
        correct_answer_agent
    ],
    max_iterations=1
)

# The feedback branch now contains the new teaching_loop.
conditional_feedback_branch = SequentialAgent(
    name="ConditionalFeedbackOrchestrator",
    sub_agents=[
        GatekeeperAgent(
            name="FeedbackGatekeeper", 
            state_key_to_check="feedback_status", 
            required_value="needs_feedback"
        ),
        teaching_loop  # The multi-turn conversation happens here
    ]
)

# The master orchestrator for per-question processing (root_agent)
question_pipeline = SequentialAgent(
    name="QuestionProcessor",
    sub_agents=[
        knowledge_agent, 
        FeedbackTriageAgent(), 
        conditional_praise_branch, 
        conditional_feedback_branch
    ]
)

# --- The master orchestrator for the final summary phase ---
summary_pipeline = SequentialAgent(
    name="SummaryPipeline",
    sub_agents=[
        summarization_agent,  # Step 1: Create the text summary
        audio_script_agent,   # Step 2: Convert summary to a script
        tts_agent             # Step 3: Convert script to an MP3 file
    ]
)
# ==============================================================================