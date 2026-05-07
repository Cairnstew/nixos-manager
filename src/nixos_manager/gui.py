"""GUI interface for the NixOS Manager agent."""

from .bot import get_bot
import gradio as gr


def create_ui():
    bot = get_bot()

    def chat_fn(message, history):
        """
        Processes the user message. 
        Qwen-Agent requires a list of dicts: [{'role': 'user', 'content': '...'}]
        """
        # Wrap the string message for the agent
        messages = [{"role": "user", "content": message}]
        
        # bot.run now receives the correctly formatted list
        for response in bot.run(messages):
            if isinstance(response, list) and len(response) > 0:
                yield response[-1].get("content", "")
            elif isinstance(response, dict):
                yield response.get("content", "")
            else:
                yield str(response)

    with gr.Blocks(title="NixOS Manager") as app:
        gr.Markdown("# 🧠 NixOS Manager")
        gr.Markdown("Interactive NixOS configuration management")

        gr.ChatInterface(
            fn=chat_fn,
            title="NixOS Manager Agent"
        )

    return app


def main():
    app = create_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        debug=True
    )


if __name__ == "__main__":
    main()