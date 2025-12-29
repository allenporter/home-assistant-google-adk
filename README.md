# Google ADK for Home Assistant

This is a custom component for Home Assistant that integrates the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/). It allows you to create conversational agents powered by Google's Gemini models directly within Home Assistant.

## Features

-   **Conversational Agent**: Chat with Gemini models via Home Assistant's Assist interface.
-   **Configurable Models**: Choose your preferred Gemini model (e.g., `gemini-3-flash-preview`).
-   **Custom Instructions**: Define the persona and instructions for your agent.

## Installation

### HACS (Recommended)

1.  Open HACS in Home Assistant.
2.  Go to **Integrations** > **Top right menu** > **Custom repositories**.
3.  Add `https://github.com/allenporter/home-assistant-google-adk` with category **Integration**.
4.  Click **Add** and then download the integration.
5.  Restart Home Assistant.

### Manual Installation

1.  Download the `custom_components/google_adk` folder from this repository.
2.  Copy it to your Home Assistant `config/custom_components/` directory.
3.  Restart Home Assistant.

## Configuration

1.  **Get a Google API Key**:
    -   Visit [Google AI Studio](https://aistudio.google.com/) to generate an API key.

2.  **Add Integration**:
    -   Go to **Settings** > **Devices & Services**.
    -   Click **Add Integration** and search for **Google ADK**.
    -   Enter your **API Key**.

    ![Config Flow Screenshot](docs/images/config_flow.png)

3.  **Configure Agent**:
    -   Once added, you can configure the agent's model and instructions via the integration options.


    ### Agent Configuration Options

    When creating or editing an agent, you can configure the following fields. These settings are crucial for defining the agent's identity and behavior, especially as you expand to multi-agent systems. See [Defining the Agent's Identity and Purpose](https://google.github.io/adk-docs/agents/llm-agents/#defining-the-agents-identity-and-purpose) in the ADK documentation for more details.

    -   **Name**: A unique identifier for the agent (e.g., `kitchen_assistant`). This is used internally and by other agents to reference this agent.
    -   **Model**: The Gemini model to use (e.g., `gemini-3-flash-preview`). Different models offer different trade-offs between speed, cost, and capability.
    -   **Description**: A concise summary of what the agent does (e.g., "Handles kitchen-related queries and timer management"). In multi-agent systems, this description helps router agents decide when to hand off tasks to this agent.
    -   **Instructions**: The core personality and rules for the agent. This defines how the agent should behave, what tone it should use, and any specific constraints. You can use Home Assistant templates here to inject dynamic context.
    -   **Tools (optional)**: Select one or more tools that the agent can use to interact with Home Assistant entities or services. Tools extend the agent's capabilities beyond conversation, enabling it to take actions in your smart home.
    -   **Subagents (optional)**: Select one or more other Google ADK agents (subagents) that this agent can delegate tasks to. Subagents allow you to build complex, multi-agent workflows by composing specialized agents together. Subagents are referenced by their unique subentry ID and can be from any other Google ADK config entry.

## Usage

1.  Go to the **Assist** icon (top right) in Home Assistant.
2.  Select the **Google ADK** agent from the dropdown.
3.  Start chatting!


## Tools and Subagents

### Tools

Tools allow your agent to interact with Home Assistant entities and call services. When configuring an agent, you can optionally select from available tools to grant the agent additional capabilities, such as turning on lights, setting scenes, or running automations. Tools are optional—if none are selected, the agent will only provide conversational responses.

### Subagents

Subagents enable advanced multi-agent workflows. You can optionally select one or more other Google ADK agents as subagents for your agent. This allows your agent to delegate tasks to specialized subagents, enabling more modular and scalable assistant designs. Subagents are referenced by their unique subentry ID and can be selected from any existing Google ADK agent configuration. If no subagents are selected, the agent will operate independently.


## Future Work

The following advanced ADK features are planned for future development:

1. **Planner support**: Integrate ADK's planning capabilities for LLM agents.
2. **Expose agent thinking**: Make intermediate agent reasoning/thoughts visible in Home Assistant, with configuration options to enable/disable or control visibility.
3. **Sessions and memory**: Support ADK session and memory APIs. The question of session/memory interop with Home Assistant is left open for future exploration.
4. **Persistent memory and storage**: Design persistent memory for agents (distinct from session memory), with configuration options for enabling and selecting storage backends.
5. **Memory ingestion strategies**: Implement memory ingestion (e.g., update memory every X turns or on-demand), referencing advanced ADK concepts.
6. **Expose memory tools**: Provide tools for agents to interact with memory (read/write/query), and consider supporting multiple memory stores (e.g., per-agent memory as a configurable option).

### Further Considerations

1. Memory will be isolated per agent by default.
2. Configuration and options flow will be used to manage these features.
3. UI/UX and privacy/performance tradeoffs for memory/session data will be considered as features are designed.

## Development

To set up the development environment:

```shell
uv venv
source .venv/bin/activate
uv pip install -r requirements_dev.txt
```

Run home assistnat locally:

```shell
./.devcontainer/develop
```

Run tests:

```shell
pytest
```
