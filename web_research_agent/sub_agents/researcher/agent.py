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
from google.genai.types import Content, Part
from google.adk.tools import google_search
from pydantic import BaseModel, Field

from . import prompt

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
        
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Initializing research context...")]),
            actions=EventActions(state_delta={"user_question": user_question})
        )

# --- Specialist Agents ---

query_generator_agent = LlmAgent(
    name="QueryGeneratorAgent",
    model="gemini-2.0-flash",
    instruction=prompt.QUERY_GENERATOR_PROMPT,
    output_schema=SearchQueries,
    output_key="search_queries",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

researcher_agent = LlmAgent(
    name="ResearcherAgent",
    model="gemini-2.0-flash",
    instruction=prompt.RESEARCHER_PROMPT,
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
                all_summaries.append(summary)

        ctx.session.state["all_research_summaries"] = all_summaries
        ctx.session.state["search_queries"] = None

reflector_agent = LlmAgent(
    name="ReflectorAgent",
    model="gemini-2.0-flash",
    instruction=prompt.REFLECTOR_PROMPT,
    output_schema=Reflection,
    output_key="reflection_result",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

summarizer_agent = LlmAgent(
    name="SummarizerAgent",
    model="gemini-2.0-flash",
    instruction=prompt.SUMMARIZER_PROMPT,
    output_key="final_summary",
)

class ShouldContinueResearch(BaseAgent):
    """Checks the reflection result to decide if the research loop should continue."""
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        reflection = ctx.session.state.get("reflection_result")
        should_stop = True
        
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
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=f"Information not sufficient. New queries: {follow_up}")]),
                actions=EventActions(
                    state_delta={"search_queries": {"queries": follow_up}}
                ),
            )
        
        if should_stop:
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

research_team_agent = SequentialAgent(
    name="ResearchTeam",
    sub_agents=[
        SetupAgent(name="SetupAgent"),
        query_generator_agent,
        research_loop,
        summarizer_agent,
    ],
) 