import asyncio
from typing import AsyncGenerator, List, Optional, Literal
from google.adk.agents import (
    LlmAgent,
    SequentialAgent,
    LoopAgent,
    BaseAgent,
)
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
# --- THIS IS THE CRUCIAL IMPORT ---
from google.genai.types import Content, Part
# --- END OF IMPORT ---
from google.adk.tools import google_search
from pydantic import BaseModel, Field

# Define the possible intents
class TriageResult(BaseModel):
    intent: Literal["research", "chitchat"] = Field(
        description="Classify the user's intent as either 'research' or 'chitchat'."
    )

# Create the Triage Agent
triage_agent = LlmAgent(
    name="TriageAgent",
    model="gemini-2.0-flash",  # A fast, cheap model is perfect for this
    instruction="You are a request classifier. Your task is to determine if the user's message is a genuine research query or simple chitchat (like 'hello', 'thank you', 'ok').",
    output_schema=TriageResult,
    output_key="triage_result"
)

# --- Pydantic Schemas for Structured LLM Output ---

class SearchQueries(BaseModel):
    queries: List[str] = Field(
        description="A list of 3-5 diverse and effective web search queries."
    )

class Reflection(BaseModel):
    is_sufficient: bool = Field(
        description="Is the information sufficient to answer the original question?"
    )
    follow_up_queries: Optional[List[str]] = Field(
        default=None, description="New search queries to fill knowledge gaps, if any."
    )

# --- Setup Agent to Persist User Question ---

class SetupAgent(BaseAgent):
    """
    This agent runs first. It takes the initial user message from the context
    and saves it to the 'user_question' state key.
    """
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_question = ""
        if ctx.user_content and ctx.user_content.parts:
            user_question = ctx.user_content.parts[0].text or ""
        
        # --- FIX: Wrap string content in Content/Part objects ---
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Initializing research context...")]),
            actions=EventActions(state_delta={"user_question": user_question})
        )

# --- Specialist Agents ---

query_generator_agent = LlmAgent(
    name="QueryGeneratorAgent",
    model="gemini-2.0-flash",
    instruction="Based on the user's question: `{user_question}`, generate a list of diverse search queries to research the topic thoroughly.",
    output_schema=SearchQueries,
    output_key="search_queries",
)

researcher_agent = LlmAgent(
    name="ResearcherAgent",
    model="gemini-2.0-flash",
    instruction="You are a web researcher. Take the provided search query: `{current_query}` and use the `google_search` tool to find the most relevant and up-to-date information. Provide a concise summary of your findings.",
    tools=[google_search],
    output_key="current_research_summary",
)

class ResearchManagerAgent(BaseAgent):
    """Orchestrates research for a list of queries."""
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        search_queries_obj = ctx.session.state.get("search_queries")
        queries = []
        if isinstance(search_queries_obj, SearchQueries):
            queries = search_queries_obj.queries
        elif isinstance(search_queries_obj, dict):
            queries = search_queries_obj.get('queries', [])

        all_summaries = ctx.session.state.get("all_research_summaries", [])

        if not queries:
            yield Event(author=self.name, content=Content(parts=[Part(text="No new search queries to process.")]))
            return

        yield Event(
            author=self.name,
            content=Content(parts=[Part(text=f"Starting research with {len(queries)} queries: {', '.join(queries)}")])
        )

        for query in queries:
            ctx.session.state["current_query"] = query
            async for event in researcher_agent.run_async(ctx):
                yield event
            
            summary = ctx.session.state.get("current_research_summary")
            if summary:
                all_summaries.append(f"Summary for query '{query}':\n{summary}")

        ctx.session.state["all_research_summaries"] = all_summaries
        ctx.session.state["search_queries"] = None

reflector_agent = LlmAgent(
    name="ReflectorAgent",
    model="gemini-2.0-flash",
    instruction="Analyze the following research summaries:\n---\n{all_research_summaries}\n---\n"
                "Compare them against the original user question: `{user_question}`. "
                "Is the information sufficient to provide a comprehensive answer? "
                "If not, what specific information is missing? Generate new, targeted search queries to fill these knowledge gaps.",
    output_schema=Reflection,
    output_key="reflection_result",
)

summarizer_agent = LlmAgent(
    name="SummarizerAgent",
    model="gemini-2.0-flash",
    instruction="You are a research report writer. Based on the original user question: `{user_question}` and the collective research summaries below, write a comprehensive, final answer. Make sure to cite your sources using the format [Source Title](URL) where appropriate, based on the web_research results.\n\n"
                "SUMMARIES:\n---\n{all_research_summaries}\n---",
)

class ShouldContinueResearch(BaseAgent):
    """Checks the reflection result to decide if the research loop should continue."""
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        reflection = ctx.session.state.get("reflection_result")
        should_stop = True
        
        # Check if reflection is a valid Pydantic model or a dict representation
        if isinstance(reflection, Reflection):
            is_sufficient = reflection.is_sufficient
            follow_up = reflection.follow_up_queries
        elif isinstance(reflection, dict):
            is_sufficient = reflection.get('is_sufficient', True)
            follow_up = reflection.get('follow_up_queries')
        else:
            is_sufficient = True
            follow_up = None

        if not is_sufficient and follow_up:
            should_stop = False
            # --- FIX: Wrap string content in Content/Part objects ---
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=f"Information not sufficient. New queries: {follow_up}")]),
                actions=EventActions(
                    state_delta={"search_queries": {"queries": follow_up}}
                ),
            )
        
        if should_stop:
            # --- FIX: Wrap string content in Content/Part objects ---
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text="Information is sufficient. Proceeding to final summary.")]),
                actions=EventActions(escalate=True)
            )

# --- Workflow Agents ---

research_loop = LoopAgent(
    name="ResearchLoop",
    sub_agents=[
        ResearchManagerAgent(name="ResearchManager"),
        reflector_agent,
        ShouldContinueResearch(name="LoopController"),
    ],
    max_iterations=3,
)

# First, let's rename our existing root_agent to be a sub-agent
research_team_agent = SequentialAgent(
    name="ResearchTeam",
    sub_agents=[
        SetupAgent(name="SetupAgent"),
        query_generator_agent,
        research_loop,
        summarizer_agent,
    ],
)


# Now, create the NEW Root Agent which acts as a router
class RootRouterAgent(BaseAgent):
    """
    This agent acts as the main entry point. It first runs a TriageAgent
    to classify the user's intent. If the intent is 'research', it
    invokes the full research team. If it's 'chitchat', it responds
    with a simple acknowledgment and stops.
    """
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Step 1: Run the Triage Agent
        yield Event(author=self.name, content=Content(parts=[Part(text="Analyzing user intent...")]))
        async for event in triage_agent.run_async(ctx):
            yield event # Pass through triage agent's events

        # Step 2: Check the result and decide what to do
        triage_result = ctx.session.state.get("triage_result")
        
        intent = ""
        if isinstance(triage_result, TriageResult):
            intent = triage_result.intent
        elif isinstance(triage_result, dict):
            intent = triage_result.get('intent', 'chitchat')

        if intent == "research":
            # Intent is research, so run the full team
            yield Event(author=self.name, content=Content(parts=[Part(text="Research query identified. Starting research team...")]))
            async for event in research_team_agent.run_async(ctx):
                yield event
        else:
            # Intent is chitchat, so just give a simple response and stop.
            yield Event(author=self.name, content=Content(parts=[Part(text="You're welcome!")]))

# --- UPDATE THE FINAL root_agent VARIABLE ---
# This is now the entry point for the entire application.
root_agent = RootRouterAgent(name="RootRouter")