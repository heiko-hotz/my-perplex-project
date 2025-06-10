from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from typing import Literal

from . import prompt

# Define the possible intents
class TriageResult(BaseModel):
    intent: Literal["research", "chitchat"] = Field(
        description="Classify the user's intent as either 'research' or 'chitchat'."
    )

# Create the Triage Agent
triage_agent = LlmAgent(
    name="TriageAgent",
    model="gemini-2.0-flash",
    # model="gemini-2.5-pro-preview-06-05",
    instruction=prompt.TRIAGE_PROMPT,
    output_schema=TriageResult,
    output_key="triage_result",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
) 