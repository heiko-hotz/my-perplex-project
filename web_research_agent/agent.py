from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai.types import Content, Part
from datetime import datetime

from .sub_agents.triage.agent import triage_agent, TriageResult
from .sub_agents.researcher.agent import research_team_agent
from .sub_agents.summarizer.agent import final_answer_agent
from .sub_agents.chitchat.agent import chitchat_agent

class ResearchCoordinatorAgent(BaseAgent):
    """
    This agent acts as the main entry point. It first runs a TriageAgent
    to classify the user's intent. If the intent is 'research', it
    invokes the full research team. If it's 'chitchat', it responds
    with a simple acknowledgment and stops.
    """
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ctx.session.state["current_time"] = f"The current time is: {current_time}"
        # Step 1: Run the Triage Agent
        yield Event(
            author=self.name, 
            content=Content(parts=[Part(text="Analyzing user intent...")]),
            actions=EventActions(
                state_delta={"current_time": current_time}
            )
        )
        async for event in triage_agent.run_async(ctx):
            yield event

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
                if event.author == "SummarizerAgent":
                    # The FinalAnswerAgent will produce the definitive response.
                    # We need to persist the state delta from the summarizer,
                    # but without showing its content to the user.
                    if event.actions.state_delta:
                        yield Event(
                            author=event.author,
                            actions=EventActions(
                                state_delta=event.actions.state_delta
                            ),
                            invocation_id=event.invocation_id,
                        )
                    continue
                yield event
            async for event in final_answer_agent.run_async(ctx):
                yield event
        else:
            # Intent is chitchat, so just give a simple response and stop.
            async for event in chitchat_agent.run_async(ctx):
                yield event

root_agent = ResearchCoordinatorAgent(name="ResearchCoordinator") 