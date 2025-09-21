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
from datetime import datetime

from textwrap import dedent
from pathlib import Path
from gtts import gTTS

from prompts import (
    KNOWLEDGE_AGENT_INSTRUCTION,
    QUESTION_ORCHESTRATOR_INSTRUCTION,
    CORRECT_ANSWER_INSTRUCTION, 
    INTERACTIVE_TEACHING_INSTRUCTION,
    SUMMARIZATION_AGENT_INSTRUCTION,
    AUDIO_SCRIPT_AGENT_INSTRUCTION,
    TTS_AGENT_INSTRUCTION
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
# SECTION 2: ENHANCED PYDANTIC SCHEMAS
# ==============================================================================

class KnowledgeResponse(BaseModel):
    is_correct: bool = Field(description="True if the student's answer is fundamentally correct.")
    needs_feedback: bool = Field(description="True if the student could benefit from guided feedback.")
    misconceptions: List[str] = Field(description="A list of specific conceptual errors.")
    missing_steps: List[str] = Field(description="A list of important logical or calculation steps omitted.")
    key_concepts: List[str] = Field(description="A list of the core physics concepts for the question.")
    hint: str = Field(description="A gentle Socratic question to guide the student.")
    confidence: str = Field(description="Confidence in the evaluation: 'high', 'medium', or 'low'.")

class TeachingResponse(BaseModel):
    teaching_response: str = Field(description="The complete, conversational script.")

class CorrectAnswerResponse(BaseModel):
    correct_answer_response: str = Field(description="The complete, conversational script.")

class SummaryResponse(BaseModel):
    session_overview: str = Field(description="A brief summary of the topics covered and student performance.")
    key_concepts_and_formulas: str = Field(description="A list of the most important concepts and formulas from the session.")
    common_misconceptions_addressed: str = Field(description="A summary of recurring errors or misconceptions.")
    areas_for_further_study: str = Field(description="Actionable advice for what the student should study next.")

class AudioScriptResponse(BaseModel):
    script: str = Field(description="The complete, conversational script for the audio summary.")

# ==============================================================================
# SECTION 3: ENHANCED TOOLS
# ==============================================================================

# --- Enhanced Human Interaction Tool ---
def human_interaction_tool(tool_context: ToolContext, prompt: str) -> dict:
    """
    Enhanced human interaction tool with better conversation management.
    Pauses execution, displays a prompt, waits for input, and returns a status.
    This tool manages turn counting and enforces the 3-turn limit with improved UX.
    """
    history = tool_context.state.get("conversation_history", [])
    curr_turn = len(history) // 2 + 1
    total_exchanges = len(history) // 2

    # Enhanced conversation state display
    print("\n" + "="*60)
    print(f"💬 INTERACTIVE LEARNING SESSION - Turn {curr_turn}/3")
    print(f"   Total exchanges completed: {total_exchanges}")
    print("="*60)

    human_input = "I'm not sure"   # default response if nothing entered
    
    # Enhanced prompt display
    print(f"\n🤖 GradeAnt+ Physics Tutor:")
    print(f"   {prompt}")
    print("\n" + "-"*40)
    
    try:
        human_input = input("Your response: ").strip()
        if not human_input:
            human_input = "I'm not sure"
            print(f"   (Using default response: '{human_input}')")
    except (KeyboardInterrupt, EOFError):
        human_input = "exit"
        print("\n   Session interrupted by user")
    
    logger.info(f"HumanTool: Turn {curr_turn} - Received input: '{human_input}'")
    
    # Update conversation history BEFORE making the status decision
    history.append({"role": "agent", "content": prompt})
    history.append({"role": "user", "content": human_input})
    tool_context.state["conversation_history"] = history
    
    # Enhanced logging
    print(f"\n📝 Conversation updated (now {len(history)} total messages)")

    # Enhanced status decision logic
    exit_keywords = ['exit', 'skip', 'quit', 'done', 'stop', 'end']
    if human_input.lower() in exit_keywords:
        logger.info("HumanTool: User requested to end conversation.")
        print("📚 User requested to end the learning session.")
        status = "completed"
    elif curr_turn >= 3:
        logger.info("HumanTool: Maximum turns reached.")
        print("⏰ Maximum learning turns completed.")
        status = "completed"
    else:
        status = "continue"
        print(f"🔄 Continuing to turn {curr_turn + 1}...")
        
    return {
        "human_response": human_input, 
        "status": status, 
        "completed_turns": curr_turn,
        "total_messages": len(history)
    }


# --- Enhanced Text-to-Speech Tool ---
def text_to_speech_tool(tool_context: ToolContext, script_text: str) -> dict:
    """
    Enhanced TTS tool with better error handling and file management.
    Converts a given text script into an MP3 audio file and saves it.
    """
    logger.info("TTS Tool: Starting enhanced audio conversion.")
    
    if not script_text or len(script_text.strip()) == 0:
        logger.error("TTS Tool: Empty script provided")
        return {"audio_file_path": None, "error": "No script text provided"}
    
    try:
        # Check if a target audio path is set in the session state
        target_audio_path = tool_context.state.get("target_audio_path")
        
        if target_audio_path:
            output_path = Path(target_audio_path)
            logger.info(f"TTS Tool: Using target path: {output_path}")
        else:
            # Fixed fallback path naming without problematic logging access
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"audio_summary_{timestamp}.mp3"
            logger.info(f"TTS Tool: Using timestamped fallback path: {output_path}")
        
        # Ensure the directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Enhanced script preprocessing
        # Remove any markdown formatting that might interfere with TTS
        clean_script = script_text.replace('**', '').replace('*', '').replace('#', '')
        
        # Add natural pauses for better speech flow
        clean_script = clean_script.replace('.', '. ').replace('!', '! ').replace('?', '? ')
        
        # Create the gTTS object with enhanced parameters
        tts = gTTS(
            text=clean_script, 
            lang='en', 
            slow=False,
            tld='com'  # Use .com domain for better voice quality
        )
        
        logger.info(f"TTS Tool: Processing {len(clean_script)} characters of script text")
        logger.info(f"WAIT...")
        tts.save(str(output_path))
        
        # Enhanced file verification
        if output_path.exists() and output_path.stat().st_size > 0:
            file_size = output_path.stat().st_size
            logger.info(f"TTS Tool: Audio file successfully created - size: {file_size:,} bytes")
            
            # Additional quality check - ensure minimum expected size
            min_expected_size = len(clean_script) * 50  # Rough estimate: 50 bytes per character
            if file_size < min_expected_size:
                logger.warning(f"TTS Tool: Audio file smaller than expected ({file_size} < {min_expected_size})")
            
            return {
                "audio_file_path": str(output_path),
                "file_size_bytes": file_size,
                "script_length_chars": len(clean_script)
            }
        else:
            logger.error("TTS Tool: Audio file was not created or is empty")
            return {"audio_file_path": None, "error": "Audio file creation failed"}
            
    except Exception as e:
        logger.error(f"TTS Tool: Failed to generate audio file. Error: {e}")
        return {"audio_file_path": None, "error": str(e)}

# ==============================================================================
# SECTION 4: ENHANCED TOOLS INSTANCES
# ==============================================================================

# Create enhanced tool instances
human_tool = FunctionTool(func=human_interaction_tool)
tts_tool = FunctionTool(func=text_to_speech_tool)

# ==============================================================================
# SECTION 5: ENHANCED QUESTION PIPELINE
# ==============================================================================

knowledge_agent = LlmAgent(
    model=MODEL,
    name="KnowledgeAgent",
    description="Expert physics educator analyzing student responses with comprehensive pedagogical insight.",
    instruction=KNOWLEDGE_AGENT_INSTRUCTION,
    output_schema=KnowledgeResponse,
    output_key="knowledge_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

interactive_teaching_agent = LlmAgent(
    model=MODEL,
    name="InteractiveTeachingAgent",
    description="Master physics educator conducting Socratic dialogue for deep learning.",
    instruction=INTERACTIVE_TEACHING_INSTRUCTION,
    output_schema=TeachingResponse,
    output_key="teaching_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    tools=[human_tool]
)

correct_answer_agent = LlmAgent(
    model=MODEL,
    name="CorrectAnswerAgent",
    description="Expert educator providing validation and reinforcement for correct responses.", 
    instruction=CORRECT_ANSWER_INSTRUCTION,
    output_schema=CorrectAnswerResponse,
    output_key="correct_answer_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

# ==============================================================================
# SECTION 6: ENHANCED LLM ORCHESTRATOR WITH AGENTTOOLS
# ==============================================================================

# Enhanced orchestrator with better decision-making logic
question_orchestrator = LlmAgent(
    model=MODEL,
    name="QuestionOrchestrator",
    description="Intelligent tutoring system orchestrator with enhanced routing logic.",
    instruction=QUESTION_ORCHESTRATOR_INSTRUCTION,
    sub_agents=[
        interactive_teaching_agent,
        correct_answer_agent
    ]
)

# Enhanced sequential pipeline with better error handling
question_pipeline = SequentialAgent(
    name="QuestionProcessor",
    description="Comprehensive question processing pipeline with enhanced analytics.",
    sub_agents=[
        knowledge_agent, 
        question_orchestrator
    ]
)

# ==============================================================================
# SECTION 7: ENHANCED SUMMARY PIPELINE
# ==============================================================================

summarization_agent = LlmAgent(
    model=MODEL,
    name="SummarizationAgent",
    description="Expert educational content curator creating comprehensive learning analytics.",
    instruction=SUMMARIZATION_AGENT_INSTRUCTION,
    output_schema=SummaryResponse,
    output_key="final_summary",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

audio_script_agent = LlmAgent(
    model=MODEL,
    name="AudioScriptAgent",
    description="Professional educational podcast scriptwriter creating engaging audio content.",
    instruction=AUDIO_SCRIPT_AGENT_INSTRUCTION,
    output_schema=AudioScriptResponse,
    output_key="audio_script",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

tts_agent = LlmAgent(
    model=MODEL,
    name="TtsAgent",
    description="Audio generation specialist converting educational scripts to high-quality speech.",
    instruction=TTS_AGENT_INSTRUCTION,
    tools=[tts_tool],
    output_key="tts_output"
)

# Enhanced summary pipeline with better coordination
summary_pipeline = SequentialAgent(
    name="SummaryOrchestrator",
    description="Comprehensive educational summary generation and audio production pipeline.",
    sub_agents=[summarization_agent, audio_script_agent, tts_agent]
)