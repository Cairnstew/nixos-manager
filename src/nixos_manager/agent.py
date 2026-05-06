from qwen_agent.agents import Assistant
from .config.settings import LLM_CONFIG
import nixos_manager.tools.nix_search  # force side-effect import

# Define the tools available to the model
tools = ['nix_search_tool', 'code_interpreter']  # code_interpreter is built-in

# Initialize the Agent
bot = Assistant(
    llm=LLM_CONFIG,
    name='NixManager',
    description='An expert specialist in NixOS configurations.',
    system_message=(
        "You are an expert NixOS administrator. "
        "Before writing any .nix code, use the nix_search_tool to verify "
        "the correct attribute names and options. "
        "Always aim for 'perfect' Nix syntax."
    ),
    function_list=tools,
)


def main():
    """Main entry point for the NixOS manager agent."""
    messages = [{'role': 'user', 'content': 'Add a postgresql service to my nixos config.'}]
    for response in bot.run(messages):
        print(response)


if __name__ == '__main__':
    main()