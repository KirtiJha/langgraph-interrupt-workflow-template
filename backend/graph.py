from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver
from langchain_ibm import ChatWatsonx
from langchain.schema import HumanMessage, AIMessage, SystemMessage
import os
from datetime import datetime
import json
import random

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = "apextestmock"


# Initialize IBM Watson LLM
def get_watson_llm():
    try:
        return ChatWatsonx(
            model_id="meta-llama/llama-3-3-70b-instruct",
            url=os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
            apikey=os.getenv("WATSONX_API_KEY"),
            project_id=os.getenv("WATSONX_PROJECT_ID"),
            params={
                "temperature": 0.7,
                "max_tokens": 1000,
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
    user_query: str
    research_plan: str
    research_results: List[str]
    analysis: str
    final_response: str
    current_step: str
    requires_user_input: bool
    interrupt_data: Optional[Dict[str, Any]]
    conversation_history: List[Dict[str, str]]
    user_choice: Optional[str]  # Add this field for interrupt responses


# Node 1: Research Planning Interrupt
def research_planner_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to get user approval for research plan"""
    print("🔍 Planning research strategy...")

    # ALWAYS interrupt for every query - this matches your original pattern
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

    # Make sure to preserve all existing state and add the new fields
    return {
        **state,  # Preserve all existing state
        "research_plan": "Comprehensive research and analysis",
        "user_choice": user_choice,
        "current_step": "information_gathering",
    }


# Node 2: Information Gathering
def information_gatherer(state: ResearchState) -> Dict[str, Any]:
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

    # Adjust research depth based on user choice
    if user_choice == "simplified":
        system_prompt = """You are a research assistant providing simplified analysis. 
        Generate 2-3 key findings that directly address the user's question with clear, concise information."""
    elif user_choice == "focused":
        system_prompt = """You are a research assistant focusing on specific aspects.
        Generate targeted findings that address the most important aspects of the user's question."""
    else:
        system_prompt = """You are a thorough research assistant. 
        Generate comprehensive research findings covering multiple aspects of the user's question.
        Provide 4-5 detailed findings with supporting information."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=f"Research query: {state['user_query']}\nResearch plan: {state.get('research_plan', 'Standard research')}"
        ),
    ]

    response = llm.invoke(messages)

    # Simulate multiple research findings
    base_findings = response.content.split("\n")[:3]  # Take first 3 lines as findings
    research_results = [
        f"Finding {i+1}: {finding.strip()}"
        for i, finding in enumerate(base_findings)
        if finding.strip()
    ]

    # Add simulated additional findings
    if user_choice == "proceed":
        research_results.extend(
            [
                "Finding 4: Cross-referenced data from multiple authoritative sources",
                "Finding 5: Current trends and recent developments identified",
            ]
        )

    return {
        **state,  # Preserve all existing state
        "research_results": research_results,
        "current_step": "research_direction_check",
    }


# Node 3: Research Direction Interrupt
def research_direction_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to ask for research direction refinement"""
    print("🔄 Checking research direction...")

    # Only interrupt if user chose "proceed" (for comprehensive research)
    user_choice = state.get("user_choice", "proceed")

    if user_choice == "proceed":
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
        return {
            **state,  # Preserve all existing state
            "research_direction": "continue",
            "current_step": "analysis",
        }


# Node 4: Deep Analysis
def deep_analyzer(state: ResearchState) -> Dict[str, Any]:
    """Performs deep analysis of gathered information"""
    print("🧠 Analyzing information...")

    llm = get_watson_llm()

    research_summary = "\n".join(state.get("research_results", []))

    system_prompt = """You are an expert analyst. Your task is to:
    1. Synthesize the research findings into coherent insights
    2. Identify patterns, connections, and implications
    3. Prepare actionable conclusions
    4. Highlight any potential concerns or limitations
    
    Provide a structured analysis that goes beyond summarizing to offer real insight."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=f"User query: {state['user_query']}\n\nResearch findings to analyze:\n{research_summary}"
        ),
    ]

    response = llm.invoke(messages)
    analysis = response.content

    return {
        **state,  # Preserve all existing state
        "analysis": analysis,
        "current_step": "format_selection",
    }


# Node 5: Format Selection Interrupt
def format_selection_interrupt(state: ResearchState) -> Dict[str, Any]:
    """Interrupts to get formatting preference"""
    print("📝 Format selection...")

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


# Node 4: Response Generation
def response_generator(state: ResearchState) -> Dict[str, Any]:
    """Generates the final formatted response"""
    print("✍️ Crafting final response...")

    llm = get_watson_llm()

    # Get user's preferred format from state
    format_choice = state.get("format_choice", "comprehensive")

    format_instructions = {
        "comprehensive": "Create a thorough, detailed response with examples, explanations, and supporting details. Use clear headings and organize information logically.",
        "executive": "Create a concise executive summary focusing on the most critical insights and actionable recommendations.",
        "structured": "Format the response with clear sections, headings, and organized bullet points for easy scanning.",
        "conversational": "Write in a natural, conversational tone as if explaining to a colleague, while maintaining professionalism.",
        "bullet_points": "Organize the response primarily using bullet points, numbered lists, and key takeaways for quick reference.",
    }

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

    context = f"""
    Original question: {state['user_query']}
    Research findings: {'; '.join(state.get('research_results', []))}
    Analysis insights: {state.get('analysis', 'N/A')}
    """

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=context)]

    response = llm.invoke(messages)
    final_response = response.content

    # Add conversation to history
    conversation_history = state.get("conversation_history", [])
    conversation_history.extend(
        [
            {"role": "user", "content": state["user_query"]},
            {"role": "assistant", "content": final_response},
        ]
    )

    return {
        **state,  # Preserve all existing state
        "final_response": final_response,
        "current_step": "completed",
        "requires_user_input": False,
        "conversation_history": conversation_history,
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
