import discord
from discord import app_commands
import os
from config import DISCORD_TOKEN

class ZoochiniBot(discord.Client):
    def __init__(self):
        # Initialize with all intents
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # This copies the global commands over to your guild.
        await self.tree.sync()

client = ZoochiniBot()

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

# Ping command
@client.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f'Pong! Latency: {latency}ms')

# Greet command
@client.tree.command(name="greet", description="Greet a user")
async def greet(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    await interaction.response.send_message(f'Hello {member.mention}! Welcome to the server!')

# Clear messages command
@client.tree.command(name="clear", description="Clear a specified number of messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message("Please specify a positive number of messages to clear.", ephemeral=True)
        return
        
    # Defer the response since clearing messages might take time
    await interaction.response.defer(ephemeral=True)
    
    # Clear the messages
    channel = interaction.channel
    deleted = await channel.purge(limit=amount)
    
    await interaction.followup.send(f'Cleared {len(deleted)} messages!', ephemeral=True)

# Error handling
@client.tree.error
async def on_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message('You do not have the correct permissions for this command.', ephemeral=True)
    else:
        await interaction.response.send_message(f'An error occurred: {str(error)}', ephemeral=True)

def main():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()