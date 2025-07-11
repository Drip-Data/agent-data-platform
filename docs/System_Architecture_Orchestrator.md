# System Architecture: The Orchestrator Model

This document outlines the core architecture of the agent, which is built around a central "Orchestrator" model. This design separates the agent's reasoning (the "brain") from its execution capabilities (the "limbs"), creating a flexible, scalable, and powerful system.

## 1. Core Philosophy

The system operates on a simple but powerful principle: **The LLM proposes, the System executes.**

-   **The Brain (LLM)**: Responsible for all reasoning, planning, and decision-making. It formulates plans in a structured XML format.
-   **The Central Nervous System (Orchestrator)**: The `EnhancedReasoningRuntime` acts as the coordinator. It interprets the LLM's plans, dispatches tasks to the correct tools, and formats the results for the LLM to observe.
-   **The Limbs (MCP Servers)**: Each MCP server is a specialized tool (e.g., code execution, web browsing) that performs a specific function when called upon.

## 2. Architecture Diagram (Mermaid)

```mermaid
graph TD
    subgraph "User / Task Source"
        A[Task Input TaskSpec]
    end

    subgraph "Core Control Plane"
        B(TaskManager)
        C{EnhancedReasoningRuntime (Orchestrator)}
        D[ReasoningPromptBuilder]
    end

    subgraph "Reasoning & Decision"
        E[LLMClient]
        F[[Google Gemini API]]
    end

    subgraph "Tool Execution Plane"
        G[ToolScoreClient]
        subgraph "MCP Servers (The 'Tools')"
            H1[Microsandbox Server]
            H2[BrowserUse Server]
            H3[DeepSearch Server]
            H4[...]
        end
    end

    subgraph "Data Output"
        I[Trajectory Log]
    end

    %% Flow Connections
    A -- TaskSpec --> B
    B -- Dispatches Task --> C
    C -- 1. Builds Initial Prompt --> D
    D -- Prompt Template --> C
    C -- 2. Calls LLM (with Prompt) --> E
    E -- API Request --> F
    F -- XML Plan --> E
    E -- XML Plan --> C
    C -- 3. Parses XML & Decides to Execute --> G
    G -- Unified Interface Call --> H1
    G -- Unified Interface Call --> H2
    G -- Unified Interface Call --> H3
    H1 -- Result --> G
    H2 -- Result --> G
    H3 -- Result --> G
    G -- 4. Returns Tool Result --> C
    C -- 5. Injects Result into History --> E
    C -- 6. Logs Full Trajectory --> I

    %% Styling
    style C fill:#f9f,stroke:#333,stroke-width:2px
    style G fill:#bbf,stroke:#333,stroke-width:2px
```

## 3. Step-by-Step Workflow

1.  **Task Entry**: A `TaskSpec` is submitted to the `TaskManager`, which acts as the system's entry point and routes the task to the `EnhancedReasoningRuntime`.

2.  **Prompt Construction**: The `EnhancedReasoningRuntime` (our Orchestrator) begins its loop. It first calls the `ReasoningPromptBuilder` to dynamically assemble a detailed system prompt. This prompt includes the user's task, the XML rules, and a dynamically generated list of all available tools and their capabilities, fetched from the running MCP servers.

3.  **LLM Proposes a Plan**: The Orchestrator, via the `LLMClient`, sends the complete prompt to the Gemini API. Crucially, it includes `stop_sequences` (like `<execute_tools />`) in the API call. This forces the LLM to stop generating text as soon as it has finished outlining its action plan for the current step. The LLM returns a response containing its reasoning in a `<think>` block and a plan in a `<sequential>` or `<parallel>` block.

4.  **Orchestrator Parses and Dispatches**: The Orchestrator receives the XML plan. It parses the XML to understand the LLM's intent.
    - If the plan is `<sequential>`, it extracts the **first action** in the sequence.
    - If the plan is `<parallel>`, it extracts **all actions** to be run concurrently.

5.  **Unified Tool Execution**: The Orchestrator **does not call the tools directly**. Instead, it sends the standardized action(s) to the `ToolScoreClient`. This client acts as a unified gateway, responsible for routing the request to the correct MCP server based on the service name (e.g., `microsandbox`).

6.  **MCP Servers Act**: The target MCP server (e.g., `microsandbox_server`) receives the request, executes the specific action (e.g., `microsandbox_execute`), and returns the result to the `ToolScoreClient`.

7.  **Result Observation and Loop**: The `ToolScoreClient` passes the result back to the Orchestrator. The Orchestrator then:
    a. Wraps the result in a `<result>` tag.
    b. Appends it to the conversation history as a new message from the `assistant`.
    c. Logs the entire turn (thought, action, result) to the trajectory log file for future training.
    d. **Loops**, returning to Step 3 to send the updated history back to the LLM for its next decision.

This cycle continues until the LLM determines the task is complete and outputs the `Final Answer:` tag.

## 4. Key Architectural Principles

-   **Separation of Concerns**: The "thinker" (LLM) is completely decoupled from the "doers" (MCP Servers). The Orchestrator acts as the essential bridge.
-   **Dynamic Discovery**: The Orchestrator has no hard-coded knowledge of specific tools. It learns what tools are available at runtime by querying the MCP servers via the `toolscore_client`.
-   **Extensibility**: To add a new tool, one only needs to create a new MCP server that exposes its capabilities via a `get_capabilities()` method. No changes are needed in the core Orchestrator.
-   **Data-Driven by Design**: The entire architecture is built to naturally produce the high-quality `(State, Action, Observation)` data required for modern RL-based agent training.
