# Web Research Agent

This project implements a multi-agent AI application for conducting web research, built using the Google Agent Development Kit (ADK).

## Overview

The application is designed to take a user's research query, perform a series of web searches to gather information, reflect on the gathered information, and produce a comprehensive summary. It can distinguish between research questions and simple chitchat, responding appropriately to each.

## Agent Architecture

The application follows a multi-agent architecture, orchestrated by a central coordinator:

-   **`ResearchCoordinatorAgent`**: The main entry point of the application. It uses a `triage_agent` to determine the user's intent.
    -   **`triage_agent`**: A sub-agent that classifies the user's input as either a "research" query or "chitchat".
    -   **`research_team_agent`**: A sequential sub-agent that executes the full research workflow if the intent is determined to be "research".

The `research_team_agent` is composed of several specialist agents that run in a loop:

1.  **`QueryGeneratorAgent`**: Generates a set of initial search queries based on the user's question.
2.  **`ResearchManagerAgent`**: Manages the execution of the research queries using the `ResearcherAgent`.
3.  **`ResearcherAgent`**: Executes a single search query using the `google_search` tool.
4.  **`ReflectorAgent`**: Analyzes the collected information to determine if it's sufficient to answer the user's question. If not, it generates follow-up questions.
5.  **`SummarizerAgent`**: Once the research is complete, this agent synthesizes all the information into a final, comprehensive answer.

After the `research_team_agent` completes, the `ResearchCoordinatorAgent` calls one final agent:

-   **`FinalAnswerAgent`**: A dedicated presentation agent that takes the final summary from the session state and formats it cleanly for the user.

## Setup and Installation

### Prerequisites
*   Python 3.10+

### Installation
```bash
# Clone this repository
git clone https://github.com/heiko-hotz/my-perplex-project.git

# Install dependencies
pip install -r requirements.txt
```

### Configuration
Make sure you have authenticated with Google Cloud:
```bash
gcloud auth application-default login
```

## Running the Agent

You can interact with the agent using the ADK's command-line tools.

**Run in the command line:**
```bash
adk run web_research_agent
```

**Run with a web interface:**
```bash
adk web
```

Once the web server is running, navigate to the provided URL, select "web_research_agent" from the dropdown, and you can start a conversation.

## Example Interaction

```
* user: Can you explain the theory of relativity?

> Analyzing user intent...
> Research query identified. Starting research team...
> Initializing research context...
> Starting research with 5 queries: theory of relativity explanation, Einstein's theory of relativity simple, special relativity vs general relativity, evidence for theory of relativity, applications of theory of relativity
> ... (research loop continues) ...
> Information is sufficient. Proceeding to final summary.
> [Final summary of the theory of relativity]
```

## Architectural Deep Dive & Design Rationale
This section details the thinking behind key architectural choices in this agent, explaining why certain patterns were chosen over others by exploring the alternatives.

### State Management: Explicit Events via `state_delta`
**Design Principle**: In the ADK, all modifications to the shared `session.state` must be handled through explicit, trackable events.

**Implementation**: To ensure state changes are properly recorded and available to all agents, they must be yielded within an `Event` object, using the `state_delta` field in `EventActions`. Simply assigning a value to the state dictionary (e.g., `ctx.session.state["key"] = value`) only changes a local, in-memory copy for the current agent's execution and will not be persisted across agents.

```python
# In ResearchCoordinatorAgent
yield Event(
    author=self.name,
    actions=EventActions(
        state_delta={"current_time": "..."}
    )
)
```

**Considered Alternatives**:
- **Direct Modification**: The most straightforward approach would be direct assignment (`ctx.session.state["key"] = value`).
- **Rationale for Rejection**: This was rejected because it is not how the ADK Session lifecycle is designed to work. State persistence is not guaranteed and this would lead to unpredictable behavior, where state appears to be set in one agent but is missing in the next. The event-driven mechanism is crucial for predictable state management, ensuring that all state changes are explicitly tracked, auditable in the event history, and handled safely by the `SessionService`, preventing race conditions.

### Workflow Initiation: The Dedicated `SetupAgent`
**Design Principle**: The first step of any complex workflow should explicitly establish its initial conditions. In this agent, the research process begins with a dedicated `SetupAgent` whose sole responsibility is to save the user's initial question into the state.

**Implementation**: `SetupAgent` is a custom `BaseAgent` and the first element in the `ResearchTeam`'s `SequentialAgent` list. It reads `ctx.user_content` and yields an event with `state_delta={'user_question': ...}`.

**Considered Alternatives**:
- **Parent Agent Sets State**: The `ResearchCoordinatorAgent` could have set the `user_question` in the state before calling the `research_team_agent`. This was avoided because it creates tight coupling, making the `ResearchTeam` less modular and harder to test or reuse independently.
- **Access `ctx.user_content` Directly**: Subsequent agents like `QueryGeneratorAgent` could have read the question directly from `ctx.user_content`. This is fragile because `user_content` only holds the input for the *current turn*. In a multi-step loop, the original question would be lost after the first turn.
- **Use a `before_agent_callback`**: This is a viable ADK pattern that allows running a function before the agent executes. However, using a dedicated agent is more explicit and self-documenting.

**Rationale for Choice**: The chosen `SetupAgent` approach clearly defines "Step 1" of the workflow. It creates an immutable "source of truth" for the `user_question` that all subsequent agents can reliably access from the state, making the entire sequence more robust and maintainable.

### Orchestration: Programmatic Logic via `BaseAgent`
**Design Principle**: Use the simplest, most reliable tool for the job. The top-level `ResearchCoordinatorAgent` uses deterministic `if/else` logic to route user requests, rather than relying on an LLM for this critical decision.

**Implementation**: The coordinator is a custom `BaseAgent`. It invokes a `triage_agent` to classify the user's intent, inspects the resulting `triage_result` from the state, and then programmatically calls the appropriate sub-agent (`chitchat_agent` or `research_team_agent`) using `.run_async()`.

**Considered Alternatives**:
- **LLM-based Routing**: An `LlmAgent` could have been used as the coordinator. It could be instructed to look at the `triage_result` in the state and then use the `transfer_to_agent()` function to delegate to the appropriate sub-agent.
- **Rationale for Rejection**: This approach was avoided for two main reasons:
    1.  **Reliability**: An `if/else` statement is 100% deterministic. Relying on an LLM for critical top-level routing introduces a small but unnecessary chance of failure or misinterpretation.
    2.  **Cost & Latency**: The `BaseAgent` makes this decision instantly with zero LLM cost. The `LlmAgent` alternative would require an extra, unnecessary LLM call just to make a simple routing decision.

**Rationale for Choice**: This design demonstrates a key principle: use programmatic orchestration for simple, deterministic tasks. LLM-driven delegation should be reserved for more complex decisions that require nuanced natural language understanding.

### Task Isolation: Managing Context in Loops
**Design Principle**: When an agent is designed to be called repeatedly on different data (e.g., in a loop), its context must be carefully managed to ensure each execution is independent.

**Challenge**: In the `ResearchLoop`, the `ResearchManagerAgent` invokes the `ResearcherAgent` for each search query. Because the same `InvocationContext` (`ctx`) is used for each call within the loop, the conversational history (`ctx.session.events`) from previous calls in the same batch can "contaminate" the context for subsequent calls. A conversational LLM might see its own prior summaries and conclude its work is already done, rather than executing the new, distinct research task.

**Considered Alternatives**:
- **Ignoring the Issue**: Allowing the context to be contaminated leads to the observed failure mode of the agent outputting repetitive, conversational "I'm done" messages.
- **Complex Prompt Engineering**: One could try to engineer the `ResearcherAgent`'s prompt to explicitly ignore previous turns, but this is brittle and fights against the natural behavior of the conversational model.

**Best Practice / Solution**: The most robust solution, and a key consideration for future improvements, is to isolate the agent's context for each discrete task. When the `ResearchManagerAgent` calls the `ResearcherAgent` for a new query, it should ideally do so with a "clean" context that does not contain the results of other, parallel tasks from the same batch. This ensures the `ResearcherAgent` is focused only on the single query it has been given. This can be achieved by creating a new, temporary `InvocationContext` for each sub-task.

### Separation of Concerns: Synthesis vs. Presentation
**Design Principle**: A robust system separates the process of generating data from the process of presenting it. The `research_team_agent` is responsible for creating a final summary, but not for displaying it to the user.

**Implementation**:
1. The `SummarizerAgent`, the final step in the `research_team_agent` sequence, saves its complete output to `state['final_summary']`.
2. The `ResearchCoordinatorAgent` receives the events from the `research_team_agent`. When it sees the event from the `SummarizerAgent`, it intercepts it, persists the `state_delta`, but *silences the content*, preventing the raw summary from being shown to the user.
3. After the research team is finished, the coordinator explicitly calls the separate `FinalAnswerAgent`.
4. The `FinalAnswerAgent`'s only job is to read `state['final_summary']` and format it cleanly for the user.

**Considered Alternatives**:
- **Single Final Agent**: The `SummarizerAgent` could have been tasked with both summarizing the research and formatting the final answer for the user.
- **Rationale for Rejection**: This would conflate two distinct responsibilities. The "data synthesis" task is complete when a summary object is created. The "presentation" task is about user-facing formatting.

**Rationale for Choice**: This decoupling creates a more modular and flexible architecture. The core research workflow's responsibility ends when it produces a final data object (the summary). The presentation layer can then be modified or replaced entirely (e.g., to format output as JSON, build a chart, or use a different tone) without any changes to the complex research and synthesis logic. 