from .discord_client import ZoochiniBot
from .message_handler import MessageHandler
from .claude_client import ClaudeClient
from .file_processor import FileProcessor
from .drive_processor import DriveProcessor
from config import DISCORD_TOKEN, ANTHROPIC_API_KEY


def main():
    print("Starting bot...")

    file_processor = FileProcessor()
    # No need to specify credentials_dir - it will use parent directory by default
    drive_processor = DriveProcessor()
    claude_client = ClaudeClient(ANTHROPIC_API_KEY)
    message_handler = MessageHandler(
        claude_client, file_processor, drive_processor)
    bot = ZoochiniBot(message_handler)
    bot.setup_commands()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
