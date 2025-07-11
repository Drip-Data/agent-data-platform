# Agent Data Platform - System Architecture Flowchart

## Main System Flow

```mermaid
flowchart TD
    A[User Input] --> B[Main Entry Point]
    B --> C{Runtime Mode?}
    
    C -->|XML Streaming| D[Enhanced Runtime]
    C -->|Standard| E[Simple Runtime]
    
    D --> F[Task Enhancement]
    F --> G[LLM Client]
    
    G --> H[Prompt Builder]
    H --> I[LLM Provider Selection]
    I --> J{Provider Type?}
    
    J -->|OpenAI| K[OpenAI Provider]
    J -->|Gemini| L[Gemini Provider] 
    J -->|DeepSeek| M[DeepSeek Provider]
    J -->|vLLM| N[vLLM Provider]
    
    K --> O[Generate Initial XML Response]
    L --> O
    M --> O
    N --> O
    
    O --> P[Sequential Streaming Executor]
    P --> Q[Parse XML for Tool Calls]
    Q --> R{Tool Call Found?}
    
    R -->|Yes| S[Extract Tool Call]
    R -->|No| T[Check for Answer Tag]
    
    S --> U[ToolScore Manager]
    U --> V[MCP Server Selection]
    V --> W{Tool Type?}
    
    W -->|Browser| X[Browser Use Server]
    W -->|Search| Y[DeepSearch Server]
    W -->|Code| Z[MicroSandbox Server]
    W -->|File| AA[Search Tool Server]
    
    X --> BB[Execute Real Tool]
    Y --> BB
    Z --> BB
    AA --> BB
    
    BB --> CC[Tool Result]
    CC --> DD[Result Injector]
    DD --> EE[Inject Real Result into XML]
    EE --> FF[Continue LLM Processing]
    FF --> P
    
    T -->|Answer Found| GG[Generate Final Result]
    T -->|No Answer| HH[Request Continuation]
    HH --> P
    
    GG --> II[Trajectory Storage]
    II --> JJ[Performance Metrics]
    JJ --> KK[User Output]
```

## Anti-Hallucination System Flow

```mermaid
flowchart TD
    A[LLM Response Generated] --> B[XML Parser]
    B --> C[Detect Tool Calls]
    C --> D{Hallucinated Results?}
    
    D -->|Yes| E[Remove Fake Results]
    D -->|No| F[Continue Processing]
    
    E --> G[Mark for Real Execution]
    G --> H[Execute via ToolScore]
    H --> I[Get Real Result]
    I --> J[Inject Real Result]
    J --> K[Update XML Stream]
    K --> F
    
    F --> L[Validate XML Structure]
    L --> M{Valid Structure?}
    
    M -->|Yes| N[Proceed to Next Step]
    M -->|No| O[XML Correction]
    O --> L
    
    N --> P{More Tool Calls?}
    P -->|Yes| C
    P -->|No| Q[Check Answer Tag]
    
    Q -->|Found| R[Complete Task]
    Q -->|Not Found| S[Request LLM Continuation]
    S --> A
```

## Tool Management Flow

```mermaid
flowchart TD
    A[Tool Request] --> B[ToolScore Manager]
    B --> C[Tool Registry Lookup]
    C --> D{Tool Available?}
    
    D -->|Yes| E[Get Tool Definition]
    D -->|No| F[Tool Discovery]
    
    F --> G[Search MCP Tools Library]
    G --> H{Tool Found?}
    
    H -->|Yes| I[Install Tool]
    H -->|No| J[Return Error]
    
    I --> E
    E --> K[Validate Parameters]
    K --> L{Parameters Valid?}
    
    L -->|Yes| M[Route to MCP Server]
    L -->|No| N[Parameter Correction]
    
    N --> O[Auto-fix Parameters]
    O --> L
    
    M --> P{Server Type?}
    P -->|Browser| Q[Browser Use Server:8084]
    P -->|Search| R[DeepSearch Server:8086]
    P -->|Code| S[MicroSandbox Server:8085]
    P -->|File| T[Search Tool Server:8087]
    
    Q --> U[Execute Tool Action]
    R --> U
    S --> U
    T --> U
    
    U --> V[Return Result]
    V --> W[Validate Result]
    W --> X[Log Performance Metrics]
    X --> Y[Cache Result if Applicable]
```

## LLM Client Architecture

```mermaid
flowchart TD
    A[LLM Request] --> B[Input Validation Middleware]
    B --> C{Valid Input?}
    
    C -->|No| D[Auto-correction]
    C -->|Yes| E[Prompt Builder Selection]
    
    D --> F{Correction Successful?}
    F -->|Yes| E
    F -->|No| G[Return Validation Error]
    
    E --> H{Task Type?}
    H -->|Reasoning| I[Reasoning Prompt Builder]
    H -->|Code| J[Code Prompt Builder]
    H -->|Web| K[Web Prompt Builder]
    H -->|Summary| L[Summary Prompt Builder]
    
    I --> M[Build Structured Prompt]
    J --> M
    K --> M
    L --> M
    
    M --> N[Provider Detection]
    N --> O{Available Provider?}
    
    O -->|OpenAI| P[OpenAI Provider]
    O -->|Gemini| Q[Gemini Provider]
    O -->|DeepSeek| R[DeepSeek Provider]
    O -->|vLLM| S[vLLM Provider]
    
    P --> T[Generate Response]
    Q --> T
    R --> T
    S --> T
    
    T --> U[Response Validation]
    U --> V{Valid Response?}
    
    V -->|Yes| W[Response Parser Selection]
    V -->|No| X[Error Handling]
    
    W --> Y{Task Type?}
    Y -->|Reasoning| Z[Reasoning Response Parser]
    Y -->|Code| AA[Code Response Parser]
    Y -->|Web| BB[Web Actions Parser]
    
    Z --> CC[Structured Output]
    AA --> CC
    BB --> CC
    
    CC --> DD[Return Result]
```

## Memory and Context Management

```mermaid
flowchart TD
    A[Conversation Start] --> B[Initialize Session]
    B --> C[Load Previous Context]
    C --> D[Memory Manager]
    
    D --> E[Context Enrichment]
    E --> F[Add to Conversation History]
    F --> G[Process Current Request]
    
    G --> H[Update Working Memory]
    H --> I[Execute Task]
    I --> J[Store Step Results]
    
    J --> K{Task Complete?}
    K -->|No| L[Update Context]
    K -->|Yes| M[Generate Summary]
    
    L --> G
    M --> N[Store Trajectory]
    N --> O[Update Performance Metrics]
    O --> P[Session End]
```

## Error Recovery and Validation

```mermaid
flowchart TD
    A[Error Detected] --> B{Error Type?}
    
    B -->|Tool Execution| C[Tool Error Handler]
    B -->|LLM Response| D[LLM Error Handler]
    B -->|XML Parsing| E[XML Error Handler]
    B -->|Network| F[Network Error Handler]
    
    C --> G[Retry with Different Parameters]
    D --> H[Request LLM Reflection]
    E --> I[XML Structure Correction]
    F --> J[Fallback Provider]
    
    G --> K{Retry Successful?}
    H --> L{Reflection Successful?}
    I --> M{XML Fixed?}
    J --> N{Fallback Successful?}
    
    K -->|Yes| O[Continue Execution]
    K -->|No| P[Report Tool Failure]
    
    L -->|Yes| O
    L -->|No| Q[Generate Error Response]
    
    M -->|Yes| O
    M -->|No| R[Manual Intervention Required]
    
    N -->|Yes| O
    N -->|No| S[System Unavailable]
    
    O --> T[Update Error Statistics]
    P --> T
    Q --> T
    R --> T
    S --> T
```

## Data Storage and Trajectory Management

```mermaid
flowchart TD
    A[Task Execution Complete] --> B[Trajectory Processor]
    B --> C[Performance Data Collection]
    C --> D[Result Analysis]
    
    D --> E{Storage Mode?}
    E -->|Daily| F[Daily Grouping]
    E -->|Weekly| G[Weekly Grouping]  
    E -->|Monthly| H[Monthly Grouping]
    E -->|Raw| I[Raw Storage]
    
    F --> J[Group by Date]
    G --> K[Group by Week]
    H --> L[Group by Month]
    I --> M[Individual Files]
    
    J --> N[Store in JSON Lines Format]
    K --> N
    L --> N
    M --> O[Store as Individual Trajectory]
    
    N --> P[Update Metrics Database]
    O --> P
    P --> Q[Generate Performance Reports]
    Q --> R[Archive Old Data]
```

This flowchart provides a comprehensive view of the Agent Data Platform's architecture, showing the main execution flow, anti-hallucination mechanisms, tool management, error handling, and data storage systems.