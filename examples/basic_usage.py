"""Basic usage examples for ollama_agent."""

from ollama_agent import create_agent, OllamaConfig
from ollama_agent.config import AgentType
from ollama_agent.tools import CalculatorTool, DateTimeTool, ShellTool

# 1. Default agent (Qwen 2.5 7B + CodeAgent)
agent = create_agent()
# result = agent.run("What is sqrt(1764) multiplied by the number of days in a year?")

# 2. Gemma with shell access
gemma_agent = create_agent(
    OllamaConfig.gemma_4b(verbose=True, max_steps=5),
    extra_tools=[ShellTool()],
)

# 3. ToolCallingAgent (JSON tool calls)
tool_agent = create_agent(
    OllamaConfig(model="qwen2.5:7b", agent_type=AgentType.TOOL_CALLING),
    tools=[CalculatorTool(), DateTimeTool()],
)

# 4. agentrial evaluation
def demo_evaluation() -> None:
    try:
        from agentrial.types import AgentInput
        from ollama_agent.evaluation import wrap_for_agentrial
    except ImportError:
        print("agentrial not installed — skipping.")
        return

    wrapped = wrap_for_agentrial(create_agent(OllamaConfig.qwen_7b()))
    # out = wrapped(AgentInput(query="What is 6 * 7?"))
    # print(out.output, out.success, out.metadata.duration_ms)

if __name__ == "__main__":
    print("Import OK. Uncomment run() calls to use with a live Ollama instance.")
    demo_evaluation()