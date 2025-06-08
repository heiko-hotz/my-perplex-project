from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai.types import Content, Part


class FinalAnswerAgent(BaseAgent):
    """
    This agent takes the final summary from the research team and presents it
    to the user. It's the very last step, ensuring that the output is clean
    and doesn't contain any internal agent names or artifacts.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # The final summary is stored in the session state by the SummarizerAgent
        final_summary = ctx.session.state.get("final_summary", "")

        # Yield a final event with an empty author and mark it as the end of the interaction
        yield Event(
            author="",
            content=Content(parts=[Part(text=final_summary)]),
            turn_complete=True,
        )


final_answer_agent = FinalAnswerAgent(name="FinalAnswerAgent") 