from google.adk.agents import LlmAgent
from . import prompt

# Create the ChitChat Agent
chitchat_agent = LlmAgent(
    name="ChitChatAgent",
    model="gemini-2.0-flash",
    instruction=prompt.CHITCHAT_PROMPT,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
) 