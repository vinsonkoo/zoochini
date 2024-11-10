from .discord_client import ZoochiniBot
from .message_handler import MessageHandler
from .claude_client import ClaudeClient
from .file_processor import FileProcessor
from config import DISCORD_TOKEN, ANTHROPIC_API_KEY


def main():
    print("Starting bot...")
    print("Required permissions:")
    print("- View Channels")
    print("- Read Message History")
    print("- Send Messages")

    file_processor = FileProcessor()
    claude_client = ClaudeClient(ANTHROPIC_API_KEY)
    message_handler = MessageHandler(claude_client, file_processor)
    bot = ZoochiniBot(message_handler)
    bot.setup_commands()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
