import aiohttp
import discord
from discord import app_commands
from .message_handler import MessageHandler
from .file_processor import FileProcessor


class ZoochiniBot(discord.Client):
    def __init__(self, message_handler: MessageHandler):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.message_handler = message_handler
        self.file_processor = FileProcessor()

    async def setup_hook(self):
        await self.tree.sync()

    def setup_commands(self):
        @self.tree.command(name="ping", description="Check the bot's latency")
        async def ping(interaction: discord.Interaction):
            latency = round(self.latency * 1000)
            await interaction.response.send_message(f'Pong! Latency: {latency}ms')

        @self.tree.command(name="ask", description="Ask Claude a question with optional image/file")
        @app_commands.describe(
            question="Your question for Claude",
            file="Optional file or pasted image to analyze"
        )
        async def ask(interaction: discord.Interaction, question: str, file: discord.Attachment = None):
            await self.message_handler.handle_ask_command(interaction, question, file)

        @self.tree.command(name="ask_drive", description="Ask Claude about a Google Drive document")
        async def ask_drive(interaction: discord.Interaction, doc_id: str, question: str):
            await self.message_handler.handle_ask_drive_command(interaction, doc_id, question)

        @self.tree.command(name="list_folder", description="List contents of a Google Drive folder")
        async def list_folder(interaction: discord.Interaction, folder_id: str):
            await self.message_handler.handle_list_folder_command(interaction, folder_id)

        @self.tree.command(name="ask_folder", description="Ask Claude about all documents in a folder")
        async def ask_folder(interaction: discord.Interaction, folder_id: str, question: str):
            await self.message_handler.handle_ask_folder_command(interaction, folder_id, question)

        @self.tree.command(name="search_drive", description="Search for files or folders by name")
        async def search_drive(interaction: discord.Interaction, name: str, type: str = None):
            await self.message_handler.handle_search_drive_command(interaction, name, type)

        @self.tree.command(name="ask_about", description="Ask Claude about files matching a name")
        async def ask_about(interaction: discord.Interaction, name: str, question: str):
            await self.message_handler.handle_ask_about_command(interaction, name, question)
