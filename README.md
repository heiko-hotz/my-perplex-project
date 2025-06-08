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

## Setup and Installation

1.  **Prerequisites**
    *   Python 3.9+
    *   Poetry

2.  **Installation**
    ```bash
    # Clone this repository
    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Configuration**
    *   Make sure you have authenticated with Google Cloud:
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

### Example Interaction

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