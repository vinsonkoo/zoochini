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

        @self.tree.command(name="ask", description="Ask Claude a question with context")
        async def ask(interaction: discord.Interaction, question: str):
            await self.message_handler.handle_ask_command(interaction, question)
