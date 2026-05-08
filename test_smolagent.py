from smolagents import CodeAgent, LiteLLMModel, Tool

# 1. Define your local model 
# We use the 'ollama/' prefix so litellm knows to route it to your local instance
model = LiteLLMModel(
    model_id="ollama/qwen3.5:9b", 
    api_base="http://localhost:11434", # Default Ollama port
    api_key="none", # Ollama doesn't require a key, but litellm needs a placeholder
    flatten_messages_as_text=False
)

# 2. Create the agent
# CodeAgent allows the LLM to write and execute Python code to solve tasks
agent = CodeAgent(tools=[], model=model)

# 3. Run the agent
agent.run("What is the square root of 144 plus 50?")