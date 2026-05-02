import os
from qwen_agent.agents import Assistant

# 1. Setup Configuration using your ENV vars
# We pull from the environment, but provide your specific values as defaults
model_name = os.getenv("NIXMGR_MODEL", "qwen2.5-coder:8b")
api_base = os.getenv("NIXMGR_SERVER", "http://localhost:11434/v1")
api_key = os.getenv("NIXMGR_API_KEY", "ollama")

def test_ollama_qwen():
    # Define the LLM configuration
    llm_cfg = {
        # Point to your local Ollama server
        'model': model_name,
        'model_server': api_base,
        'api_key': api_key,
        
        # Optional: Set generate parameters
        'generate_cfg': {
            'top_p': 0.8,
            'temperature': 0.7,
        }
    }

    # Initialize the Assistant
    bot = Assistant(llm=llm_cfg, name='QwenTester', description='A test agent running on Ollama')

    # Prepare a simple message
    messages = [{'role': 'user', 'content': 'Hello! Can you confirm you are running via Ollama?'}]

    print(f"--- Sending request to {api_base} using {model_name} ---")
    
    # Run the agent and stream the response
    response_content = ""
    for responses in bot.run(messages=messages):
        # qwen-agent returns a list of messages; we want the last one
        current_msg = responses[-1]['content']
        # Print only the new delta (basic streaming simulation)
        print(current_msg[len(response_content):], end='', flush=True)
        response_content = current_msg
    
    print("\n\n--- Test Complete ---")

if __name__ == "__main__":
    test_ollama_qwen()