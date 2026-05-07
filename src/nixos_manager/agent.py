from .bot import get_bot


def main():
    """Main entry point for the NixOS manager CLI agent."""
    bot = get_bot()
    messages = [{'role': 'user', 'content': 'Add a postgresql service to my nixos config.'}]
    for response in bot.run(messages):
        print(response)


if __name__ == '__main__':
    main()