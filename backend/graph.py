from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langchain_ibm import ChatWatsonx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage
import os
from datetime import datetime
import json
import random

# Load environment variables
from dotenv import load_dotenv

load_dotenv()


# Initialize IBM Watson LLM
def get_watson_llm():
    try:
        return ChatWatsonx(
            model_id="meta-llama/llama-3-3-70b-instruct",
            url=os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
            apikey=os.getenv("WATSONX_API_KEY"),
            project_id=os.getenv("WATSONX_PROJECT_ID"),
            streaming=True,
            params={
                "temperature": 0.7,
                "max_tokens": 8000,
                "top_p": 0.9,
            },
        )
    except Exception as e:
        print(f"Warning: Watson LLM initialization failed: {e}")
        # For demo purposes, we'll create a simple mock
        return MockLLM()


class MockLLM:
    """Mock LLM for demo purposes when Watson is not available"""

    def invoke(self, messages):
        return self._get_response(messages)

    async def ainvoke(self, messages):
        return self._get_response(messages)

    def _get_response(self, messages):
        class MockResponse:
            def __init__(self, content):
                self.content = content

        # Extract the human message
        human_msg = next(
            (
                msg.content
                for msg in messages
                if hasattr(msg, "content")
                and "Create a research plan" in str(msg.content)
            ),
            "",
        )

        if "Create a research plan" in human_msg:
            return MockResponse(
                '{"complexity": "moderate", "research_areas": ["General research", "Background information"], "estimated_time": 3, "requires_deep_analysis": true, "plan_description": "Comprehensive research and analysis"}'
            )
        elif "Research query:" in human_msg:
            return MockResponse(
                "This is a comprehensive analysis of your query. Key findings include important insights and relevant information that addresses your question thoroughly."
            )
        elif "Synthesize the research findings" in human_msg:
            return MockResponse(
                "Based on the research findings, I can provide a detailed analysis with actionable insights and recommendations."
            )
        else:
            return MockResponse(
                "Thank you for your question. Based on my analysis, here's a comprehensive response that addresses your inquiry with detailed information and practical insights."
            )


# State definition for the intelligent research assistant
class ResearchState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]  # LangGraph messages pattern
    user_query: str
    research_plan: str
    research_results: List[str]
    analysis: str
    final_response: str
    current_step: str
    requires_user_input: bool
    interrupt_data: Optional[Dict[str, Any]]
    user_choice: Optional[str]  # Add this field for interrupt responses
    # Fields for follow-up support
    format_choice: Optional[str]  # User's preferred response format
    research_direction: Optional[str]  # Direction for further research


# Node 1: Research Planning with Interrupt
async def research_planner_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to get user approval for research plan"""
    print("🔍 Planning research strategy...")

    # Check if this is a follow-up question by examining message history
    messages = state.get("messages", [])
    has_previous_conversation = len(messages) > 0

    # Extract previous context from messages if available
    previous_query = ""
    previous_response = ""

    if has_previous_conversation:
        # Find the last user and assistant message pair
        user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]

        if user_messages:
            previous_query = user_messages[-1].content
        if ai_messages:
            previous_response = ai_messages[-1].content

    is_followup = bool(previous_query and previous_response)

    if is_followup:
        interrupt_msg = f"""## Follow-up Question Analysis

**Previous Question**: {previous_query}

**Current Question**: {state['user_query']}

I can see this is a follow-up to our previous conversation. I'm ready to research this new question while considering our previous discussion context.

Please choose how you'd like me to proceed:

- **proceed**: Full comprehensive research with detailed analysis
- **simplified**: Quick overview with key points  
- **focused**: Targeted research on specific aspects
- **continue_context**: Build upon our previous conversation
- **cancel**: Stop the research process

How would you like me to approach this follow-up research?"""
    else:
        # Original interrupt message for new conversations
        interrupt_msg = f"""## Research Query Analysis

I've analyzed your question: **"{state['user_query']}"**

I'm ready to conduct comprehensive research on this topic. Please choose how you'd like me to proceed:

- **proceed**: Full comprehensive research with detailed analysis
- **simplified**: Quick overview with key points  
- **focused**: Targeted research on specific aspects
- **cancel**: Stop the research process

How would you like me to approach this research?"""

    user_choice = interrupt(interrupt_msg)

    print(f"DEBUG: User selected in research_planner_interrupt: {user_choice}")

    # Add the current user query to messages
    new_messages = [HumanMessage(content=state["user_query"])]

    # Make sure to preserve all existing state and add the new fields
    return {
        **state,  # Preserve all existing state
        "messages": new_messages,  # Add user message to conversation
        "research_plan": "Comprehensive research and analysis",
        "user_choice": user_choice,
        "current_step": "information_gathering",
    }


# Node 2: Information Gathering
async def information_gatherer(state: ResearchState) -> Dict[str, Any]:
    """Gathers information based on the approved research plan"""
    print("📚 Gathering information...")

    # Debug: Print entire state to see what's available
    print(f"DEBUG: Full state keys: {list(state.keys())}")
    print(f"DEBUG: user_choice in state: {state.get('user_choice')}")
    print(f"DEBUG: research_plan in state: {state.get('research_plan')}")

    # Get user choice from previous node or state
    user_choice = state.get("user_choice", "proceed")

    print(f"User choice: {user_choice}")

    if user_choice == "cancel":
        return {
            "research_results": ["Research cancelled by user request"],
            "current_step": "direct_response",
            "final_response": "Research was cancelled at your request.",
        }

    llm = get_watson_llm()

    # Check if this is a follow-up with context from messages
    messages = state.get("messages", [])
    has_context = len(messages) > 1  # More than just the current user message

    # Extract previous context from messages if available
    previous_query = ""
    previous_response = ""

    if has_context:
        # Find the last user and assistant message pair (before current)
        user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]

        if len(user_messages) > 1:  # Previous user message exists
            previous_query = user_messages[-2].content  # Second to last
        if ai_messages:  # Previous assistant response exists
            previous_response = ai_messages[-1].content

    # Prepare context-aware prompts for follow-up questions
    context_section = ""
    if has_context:
        context_section = f"""
        
Previous conversation context:
- Previous question: {previous_query}
- Previous response summary: {previous_response[:400]}...

Consider this context when generating research findings."""

    # Adjust research depth based on user choice
    if user_choice == "simplified":
        system_prompt = f"""You are a research assistant providing simplified analysis. 
        Generate 2-3 key findings that directly address the user's question with clear, concise information.{context_section}"""
    elif user_choice == "focused":
        system_prompt = f"""You are a research assistant focusing on specific aspects.
        Generate targeted findings that address the most important aspects of the user's question.{context_section}"""
    elif user_choice == "continue_context":
        system_prompt = f"""You are a research assistant building on previous conversation context.
        Generate research findings that build upon this context while addressing the current question.
        Provide 3-4 focused findings that connect to the previous discussion.{context_section}"""
    else:
        system_prompt = f"""You are a thorough research assistant. 
        Generate comprehensive research findings covering multiple aspects of the user's question.
        Provide 4-5 detailed findings with supporting information.{context_section}"""

    # Prepare the research query with context for all follow-up questions
    if has_context:
        research_query = f"""Current question: {state['user_query']}

Previous context:
- Previous question: {previous_query}
- Previous response: {previous_response[:300]}...

Research approach: {user_choice}
Please research the current question while considering the previous context and approach preference."""
    else:
        research_query = f"Research query: {state['user_query']}\nResearch plan: {state.get('research_plan', 'Standard research')}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=research_query),
    ]

    response = await llm.ainvoke(messages)

    # Simulate multiple research findings
    base_findings = response.content.split("\n")[:3]  # Take first 3 lines as findings
    research_results = [
        f"Finding {i+1}: {finding.strip()}"
        for i, finding in enumerate(base_findings)
        if finding.strip()
    ]

    # Add simulated additional findings based on research approach
    if user_choice == "proceed":
        research_results.extend(
            [
                "Finding 4: Cross-referenced data from multiple authoritative sources",
                "Finding 5: Current trends and recent developments identified",
            ]
        )

    # For ALL follow-up questions, add context integration finding
    if has_context:
        research_results.append(
            f"Finding {len(research_results)+1}: Context integration - Connected insights from previous discussion about '{previous_query[:50]}...'"
        )

    return {
        **state,  # Preserve all existing state
        "research_results": research_results,
        "current_step": "research_direction_check",
    }


# Node 3: Research Direction Interrupt
async def research_direction_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to ask for research direction refinement"""
    print("🔄 Checking research direction...")

    # Only interrupt if user chose "proceed" or other comprehensive options (for detailed research)
    user_choice = state.get("user_choice", "proceed")

    # Trigger interrupt for comprehensive research choices
    comprehensive_choices = ["proceed", "comprehensive"]

    if user_choice in comprehensive_choices:
        # Check if this is a follow-up conversation from messages
        messages = state.get("messages", [])
        has_context = len(messages) > 1  # More than just the current user message

        if has_context:
            direction_msg = """## Research Direction Refinement

I've gathered substantial information on your follow-up question. To provide the most valuable insights that build on our previous conversation, would you like me to explore any specific angle further?

### Available Focus Areas:
- **technical**: Deep dive into technical aspects and implementation details
- **practical**: Focus on real-world applications and use cases  
- **recent**: Emphasize latest developments and current trends
- **comparative**: Compare different approaches or solutions
- **continue**: Proceed with general comprehensive analysis
- **continue_context**: Build specifically on our previous conversation context

Which direction interests you most?"""
        else:
            direction_msg = """## Research Direction Refinement

I've gathered substantial information on your topic. To provide the most valuable insights, would you like me to explore any specific angle further?

### Available Focus Areas:
- **technical**: Deep dive into technical aspects and implementation details
- **practical**: Focus on real-world applications and use cases  
- **recent**: Emphasize latest developments and current trends
- **comparative**: Compare different approaches or solutions
- **continue**: Proceed with general comprehensive analysis

Which direction interests you most?"""

        direction_choice = interrupt(direction_msg)

        return {
            **state,  # Preserve all existing state
            "research_direction": direction_choice,
            "current_step": "analysis",
        }
    else:
        # Skip this interrupt for simplified/focused research
        # But check if this is a follow-up conversation with context from messages
        messages = state.get("messages", [])
        has_context = len(messages) > 1  # More than just the current user message

        if has_context:
            # For follow-up questions, automatically use context-aware direction
            print(
                "DEBUG: Follow-up detected, setting research_direction to 'continue_context'"
            )
            return {
                **state,  # Preserve all existing state
                "research_direction": "continue_context",
                "current_step": "analysis",
            }
        else:
            # Regular new conversation without context
            return {
                **state,  # Preserve all existing state
                "research_direction": "continue",
                "current_step": "analysis",
            }


# Node 4: Deep Analysis
async def deep_analyzer(state: ResearchState) -> Dict[str, Any]:
    """Performs deep analysis of gathered information"""
    print("🧠 Analyzing information...")

    llm = get_watson_llm()

    research_summary = "\n".join(state.get("research_results", []))
    research_direction = state.get("research_direction", "continue")

    # Check for previous context from messages
    messages = state.get("messages", [])
    has_context = len(messages) > 1  # More than just the current user message

    # Extract previous context from messages if available
    previous_query = ""
    previous_response = ""

    if has_context:
        # Find the last user and assistant message pair (before current)
        user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]

        if len(user_messages) > 1:  # Previous user message exists
            previous_query = user_messages[-2].content  # Second to last
        if ai_messages:  # Previous assistant response exists
            previous_response = ai_messages[-1].content

    # Adjust system prompt based on research direction and context
    if research_direction == "continue_context" and has_context:
        system_prompt = f"""You are an expert analyst building on previous conversation context. Your task is to:
        1. Connect the current analysis to the previous discussion
        2. Identify relationships between the previous and current topics
        3. Synthesize insights that bridge both conversations
        4. Provide contextual conclusions that show progression
        
        Previous conversation context:
        - Previous question: {previous_query}
        - Previous response: {previous_response[:400]}...
        
        Provide a structured analysis that integrates both conversations."""
    else:
        system_prompt = """You are an expert analyst. Your task is to:
        1. Synthesize the research findings into coherent insights
        2. Identify patterns, connections, and implications
        3. Prepare actionable conclusions
        4. Highlight any potential concerns or limitations
        
        Provide a structured analysis that goes beyond summarizing to offer real insight."""

    # Prepare content for analysis
    if research_direction == "continue_context" and has_context:
        content = f"""Current query: {state['user_query']}
        
Previous context:
Question: {previous_query}
Response: {previous_response[:300]}...

Current research findings to analyze:
{research_summary}"""
    else:
        content = f"User query: {state['user_query']}\n\nResearch findings to analyze:\n{research_summary}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=content),
    ]

    response = await llm.ainvoke(messages)
    analysis = response.content

    return {
        **state,  # Preserve all existing state
        "analysis": analysis,
        "current_step": "format_selection",
    }


# Node 5: Format Selection Interrupt
async def format_selection_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to get formatting preference"""
    print("📝 Format selection...")

    # Check if user_choice contains a format choice (for streaming scenarios)
    user_choice = state.get("user_choice", "")
    format_choices = [
        "comprehensive",
        "executive",
        "structured",
        "conversational",
        "bullet_points",
    ]

    print(f"DEBUG: Current user_choice: {user_choice}")
    print(f"DEBUG: Format choices: {format_choices}")
    print(f"DEBUG: Is user_choice in format_choices: {user_choice in format_choices}")

    if user_choice in format_choices:
        # User already provided format choice, skip interrupt
        print(f"Format already chosen: {user_choice}")
        return {
            **state,  # Preserve all existing state
            "format_choice": user_choice,
            "current_step": "response_formatting",
        }

    print("DEBUG: No format choice found, showing interrupt...")
    analysis = state.get("analysis", "")
    analysis_preview = analysis[:300] + "..." if len(analysis) > 300 else analysis

    format_msg = f"""## Research Complete - Choose Response Format

I've completed a detailed analysis of your question. Here's a preview:

**{analysis_preview}**

### How would you like me to present the final response?

- **comprehensive**: Thorough, detailed response with examples and explanations
- **executive**: Concise executive summary with key insights and recommendations  
- **structured**: Well-organized format with clear headings and bullet points
- **conversational**: Natural, conversational tone while maintaining professionalism
- **bullet_points**: Quick reference format with organized lists and takeaways

Which presentation style would be most helpful for you?"""

    format_choice = interrupt(format_msg)

    return {
        **state,  # Preserve all existing state
        "format_choice": format_choice,
        "current_step": "response_formatting",
    }


# Node 6: Response Generation
async def response_generator(state: ResearchState) -> Dict[str, Any]:
    """Generates the final formatted response with streaming support"""
    print("✍️ Crafting final response...")

    llm = get_watson_llm()

    # Get user's preferred format from state
    format_choice = state.get("format_choice", "comprehensive")
    research_direction = state.get("research_direction", "continue")

    # Check for previous context from messages
    messages = state.get("messages", [])
    has_context = len(messages) > 1  # More than just the current user message

    # Extract previous context from messages if available
    previous_query = ""
    previous_response = ""

    if has_context:
        # Find the last user and assistant message pair (before current)
        user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]

        if len(user_messages) > 1:  # Previous user message exists
            previous_query = user_messages[-2].content  # Second to last
        if ai_messages:  # Previous assistant response exists
            previous_response = ai_messages[-1].content
    has_context = bool(previous_query and previous_response)

    format_instructions = {
        "comprehensive": "Create a thorough, detailed response with examples, explanations, and supporting details. Use clear headings and organize information logically.",
        "executive": "Create a concise executive summary focusing on the most critical insights and actionable recommendations.",
        "structured": "Format the response with clear sections, headings, and organized bullet points for easy scanning.",
        "conversational": "Write in a natural, conversational tone as if explaining to a colleague, while maintaining professionalism.",
        "bullet_points": "Organize the response primarily using bullet points, numbered lists, and key takeaways for quick reference.",
    }

    # For follow-up questions, always use context-aware prompts regardless of research direction
    if has_context:
        # Add direction-specific guidance for follow-up questions
        direction_guidance = ""
        if research_direction == "technical":
            direction_guidance = "Focus on technical aspects, implementation details, and mathematical/scientific foundations while building on previous context."
        elif research_direction == "practical":
            direction_guidance = "Emphasize real-world applications, use cases, and practical implications while connecting to previous insights."
        elif research_direction == "recent":
            direction_guidance = "Highlight latest developments and current trends while relating to our previous discussion."
        elif research_direction == "comparative":
            direction_guidance = "Compare different approaches or solutions while building on the foundation from our previous conversation."
        else:
            direction_guidance = "Provide a comprehensive analysis that builds specifically on our previous conversation context."

        system_prompt = f"""You are creating a follow-up response that builds on previous conversation context. 

        Previous conversation:
        - Question: {previous_query}
        - Response: {previous_response[:300]}...

        Research Direction: {direction_guidance}
        Formatting style: {format_instructions.get(format_choice, format_instructions["comprehensive"])}
        
        Requirements:
        - Reference and build upon the previous conversation naturally
        - Show how the current response connects to previous insights
        - Address the user's follow-up question thoroughly
        - Maintain continuity in the conversation flow
        - Be informative, accurate, and actionable
        - Include specific examples where relevant
        - End with a summary that ties both conversations together
        """
    else:
        system_prompt = f"""You are creating a final response for the user. 

        Formatting style: {format_instructions.get(format_choice, format_instructions["comprehensive"])}
        
        Requirements:
        - Directly address the user's original question
        - Incorporate insights from the analysis
        - Be informative, accurate, and actionable
        - Maintain a professional yet approachable tone
        - Include specific examples where relevant
        - End with a brief summary or next steps if appropriate
        """

    # Prepare context information
    if research_direction == "continue_context" and has_context:
        context = f"""
        Current question: {state['user_query']}
        Previous question: {previous_query}
        Previous response summary: {previous_response[:200]}...
        Current research findings: {'; '.join(state.get('research_results', []))}
        Current analysis insights: {state.get('analysis', 'N/A')}
        """
    else:
        context = f"""
        Original question: {state['user_query']}
        Research findings: {'; '.join(state.get('research_results', []))}
        Analysis insights: {state.get('analysis', 'N/A')}
        """

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=context)]

    # Use normal invoke - streaming will be handled by astream_events
    response = await llm.ainvoke(messages)
    final_response = response.content

    # Add the assistant's response to the conversation messages
    new_messages = [AIMessage(content=final_response)]

    return {
        **state,  # Preserve all existing state
        "messages": new_messages,  # Add assistant message to conversation
        "final_response": final_response,
        "current_step": "completed",
        "requires_user_input": False,
    }


# Build the research assistant graph
def create_research_graph():
    """Creates the intelligent research assistant workflow"""
    builder = StateGraph(ResearchState)

    # Add nodes
    builder.add_node("research_planner_interrupt", research_planner_interrupt)
    builder.add_node("information_gatherer", information_gatherer)
    builder.add_node("research_direction_interrupt", research_direction_interrupt)
    builder.add_node("deep_analyzer", deep_analyzer)
    builder.add_node("format_selection_interrupt", format_selection_interrupt)
    builder.add_node("response_generator", response_generator)

    # Add edges
    builder.add_edge(START, "research_planner_interrupt")
    builder.add_edge("research_planner_interrupt", "information_gatherer")
    builder.add_edge("information_gatherer", "research_direction_interrupt")
    builder.add_edge("research_direction_interrupt", "deep_analyzer")
    builder.add_edge("deep_analyzer", "format_selection_interrupt")
    builder.add_edge("format_selection_interrupt", "response_generator")
    builder.add_edge("response_generator", END)

    # Compile with memory
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# Create the compiled graph
research_graph = create_research_graph()


# Streaming function for the research assistant
async def stream_research_response(thread_id: str, user_choice: str):
    """Stream the research workflow response with focus on final response generation"""
    print(f"\n📝 Starting streaming research for thread: {thread_id}")
    print(f"User choice: {user_choice}")

    config = {"configurable": {"thread_id": thread_id}}

    # Define nodes where we want to stream content
    STREAMING_NODES = {
        "response_generator",  # Stream the final response generation
    }

    try:
        # Check if user_choice is a format choice and update state accordingly
        format_choices = [
            "comprehensive",
            "executive",
            "structured",
            "conversational",
            "bullet_points",
        ]

        if user_choice in format_choices:
            # Get current state and update it with the format choice
            current_state = research_graph.get_state(config)
            if current_state.values:
                # Update the state to include the format choice
                updated_state = {
                    **current_state.values,
                    "format_choice": user_choice,
                    "user_choice": user_choice,
                }
                # Update the state in the graph
                research_graph.update_state(config, updated_state)

        # Resume the graph with the user's choice using Command
        # Use astream_events to capture streaming content during resume
        async for event in research_graph.astream_events(
            Command(resume=user_choice), version="v2", config=config
        ):
            # Stream LLM content from specified nodes
            if event["event"] == "on_chat_model_stream":
                current_node = event.get("metadata", {}).get("langgraph_node")
                if current_node in STREAMING_NODES:
                    data = event["data"]
                    chunk = data["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        yield {
                            "content": chunk.content,
                            "type": "content",
                            "done": False,
                            "node": current_node,
                        }

        # Final completion signal
        yield {"content": "", "type": "content", "done": True}

    except Exception as e:
        print(f"Streaming error: {str(e)}")
        yield {
            "content": f"Error in streaming: {str(e)}",
            "type": "error",
            "done": True,
        }
