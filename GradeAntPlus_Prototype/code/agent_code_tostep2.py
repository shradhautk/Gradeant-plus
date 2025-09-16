import uuid
import json
import asyncio
import logging
from typing import List, AsyncGenerator
import os
from pathlib import Path
# --- Pydantic and ADK Imports ---
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('GradeAntPlus-Step3-Interactive')
logging.getLogger('google_adk').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.ERROR)
logging.getLogger('google.genai.models').setLevel(logging.ERROR)
logging.getLogger('google.generativeai').setLevel(logging.ERROR)  # Fixed typo
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('google_genai').setLevel(logging.WARNING) # prevent AFC Call warning

code_folder = Path(os.path.dirname(os.path.abspath(__file__)))

os.chdir(code_folder)
input_dir = code_folder.parent / "input"
output_dir = code_folder.parent / "output"

# ==============================================================================
# SECTION 1: PYDANTIC OUTPUT SCHEMA (Unchanged)
# ==============================================================================
class KnowledgeResponse(BaseModel):
    is_correct: bool = Field(description="True if the student's answer is fundamentally correct.")
    needs_feedback: bool = Field(description="True if the student could benefit from guided feedback.")
    misconceptions: List[str] = Field(description="A list of specific conceptual errors.")
    missing_steps: List[str] = Field(description="A list of important logical or calculation steps omitted.")
    key_concepts: List[str] = Field(description="A list of the core physics concepts for the question.")
    hint: str = Field(description="A gentle Socratic question to guide the student.")
    confidence: str = Field(description="Confidence in the evaluation: 'high', 'medium', or 'low'.")

# ==============================================================================
# SECTION 2: HUMAN-IN-THE-LOOP TOOLS (Fixed)
# ==============================================================================

def human_interaction_tool(tool_context: ToolContext, prompt: str) -> dict:
    """Pauses execution, displays a prompt to the human, and waits for their text input."""
    logger.info(f"HumanTool: Prompting user: '{prompt[:80]}...'")
    
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
    if human_input.lower() in ['done', 'exit', 'got it', 'thanks']:
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

def exit_loop_tool(tool_context: ToolContext, reason: str) -> dict:
    """Allows the TeachingAgent to programmatically exit the conversation loop."""
    logger.info(f"ExitTool: Agent requested loop exit. Reason: {reason}")
    tool_context.actions.escalate = True  # Signal the parent LoopAgent to stop
    return {"status": "exited_by_agent", "reason": reason}

# Create the tools the agent can use
human_tool = FunctionTool(func=human_interaction_tool)
exit_tool = FunctionTool(func=exit_loop_tool)

# ==============================================================================
# SECTION 3: AGENT DEFINITIONS (TeachingAgent is updated)
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
    model="gemini-2.5-flash",  # Updated to a valid model name
    name="KnowledgeAgent",
    instruction=KNOWLEDGE_AGENT_INSTRUCTION,
    output_schema=KnowledgeResponse,
    output_key="knowledge_response"
)

# --- Agent 2: Correct Answer Agent ---
CORRECT_ANSWER_INSTRUCTION = """You are providing positive reinforcement for a correct student response.

**Context:**
- The student's answer has been marked as correct.
- Expert Analysis: {knowledge_response}

**Your Task:**
- Write a brief, encouraging message (2-3 sentences max).
- Acknowledge what the student did well, using the key concepts from the analysis.
- Reinforce their confidence.

**Example:** "Excellent work! Your application of Newton's Second Law was spot-on, and you correctly calculated the acceleration. Great job!"
"""
correct_answer_agent = LlmAgent(
    model="gemini-2.0-flash",  # Updated to a valid model name
    name="CorrectAnswerAgent",
    instruction=CORRECT_ANSWER_INSTRUCTION,
)

# --- Updated Teaching Agent ---
TEACHING_AGENT_INSTRUCTION = """You are a Socratic physics tutor in a multi-turn conversation. Your goal is to guide a student to discover their own mistake.

**CONTEXT:**
- Expert Analysis of the student's initial mistake: {knowledge_response}
- The ongoing conversation with the student: {conversation_history}

**YOUR TASK:**
1. Review the `conversation_history` to understand the current context. If the history is empty, this is the first turn.
2. Based on the `knowledge_response` and the history, formulate your NEXT Socratic question.
3. **You MUST use the `human_interaction_tool`** to ask your question and get the student's response. This is your ONLY way to talk to them.
4. If you believe the student now understands the concept based on their last response, **you MUST call the `exit_loop_tool`** with the reason "Student understands the concept."
5. Do NOT give the answer directly. Ask guiding questions.
"""
teaching_agent = LlmAgent(
    model="gemini-2.0-flash",  # Updated to a valid model name
    name="TeachingAgent",
    instruction=TEACHING_AGENT_INSTRUCTION,
    tools=[human_tool, exit_tool]  # Agent now has access to the new tools
)

# ==============================================================================
# SECTION 4: CUSTOM AGENTS FOR ORCHESTRATION (Fixed implementation)
# ==============================================================================
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

# This is the new, dedicated loop for the 3-turn teaching conversation.
teaching_loop = LoopAgent(
    name="TeachingLoop",
    sub_agents=[teaching_agent],
    max_iterations=3  # The conversation will last at most 3 turns
)

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

# The master orchestrator remains structurally the same.
question_processor = SequentialAgent(
    name="QuestionProcessor",
    sub_agents=[
        knowledge_agent, 
        FeedbackTriageAgent(), 
        conditional_praise_branch, 
        conditional_feedback_branch
    ]
)

# ==============================================================================
# SECTION 6: MAIN APPLICATION LOGIC (Simplified)
# ==============================================================================

def load_questions_from_file(filename: str) -> list:
    """Loads the list of questions from a JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not load questions from '{filename}': {e}")
        return []

async def grade_ant_plus_main(qa_file: Path):
    """Main function uses the master orchestrator to run the full process."""
    service = InMemorySessionService()
    runner = Runner(
        agent=question_processor, 
        session_service=service, 
        app_name="GradeAntPlus"
    )

    input_questions = load_questions_from_file(qa_file)
    if not input_questions:
        return

    print("--- Starting GradeAnt+ Session (with Interactive Feedback) ---")
    print(f"📊 Total questions to process: {len(input_questions)}")

    for idx, question_data in enumerate(input_questions, 1):
        print(f"\n{'='*60}")
        print(f"Processing Question {idx}/{len(input_questions)}: {question_data.get('question_id', 'UNKNOWN')}")
        print(f"{'='*60}")
        
        # Print all input data at the start
        print("\n📋 INITIAL INPUT DATA:")
        input_keys = ["question_id", "student_answer", "reference_answer", "question_text"]
        for key in input_keys:
            value = question_data.get(key, "NOT FOUND")
            if len(str(value)) > 100:
                print(f"  {key}: {str(value)[:100]}...")
            else:
                print(f"  {key}: {value}")
        
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
        print("-" * 60)

if __name__ == "__main__":
    os.system('clear')
    qa_file_path = input_dir / "qa.json"
    asyncio.run(grade_ant_plus_main(qa_file_path))
    print("\n--- All questions processed. Session complete. ---")