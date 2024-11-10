import discord
from discord import app_commands
import os
from anthropic import Anthropic
from config import DISCORD_TOKEN, ANTHROPIC_API_KEY
import aiohttp
import io
import asyncio
from PIL import Image
from PyPDF2 import PdfReader
import tempfile

class ZoochiniBot(discord.Client):
    def __init__(self):
        # Enable required intents
        intents = discord.Intents.default()
        intents.message_content = True  # For accessing message content
        intents.messages = True         # For accessing messages
        
        print("Bot intents enabled:", intents.value)  # Debug print

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

    async def setup_hook(self):
        await self.tree.sync()

client = ZoochiniBot()

def check_required_permissions(channel):
    """Check if bot has required permissions in the channel"""
    if not isinstance(channel, discord.TextChannel):
        return {'view_channel': False, 'read_message_history': False, 'send_messages': False}
        
    permissions = channel.permissions_for(channel.guild.me)
    return {
        'view_channel': permissions.view_channel,
        'read_message_history': permissions.read_message_history,
        'send_messages': permissions.send_messages
    }

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

@client.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f'Pong! Latency: {latency}ms')

@client.tree.command(name="greet", description="Greet a user")
async def greet(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    await interaction.response.send_message(f'Hello {member.mention}! Welcome to the server!')

@client.tree.command(name="clear", description="Clear a specified number of messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message("Please specify a positive number of messages to clear.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    deleted = await channel.purge(limit=amount)
    await interaction.followup.send(f'Cleared {len(deleted)} messages!', ephemeral=True)

async def extract_pdf_content(pdf_bytes):
    """Extract text content from PDF bytes"""
    try:
        # Create a temporary file to save PDF content
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf.seek(0)
            
            # Read PDF content
            reader = PdfReader(temp_pdf.name)
            text_content = []
            
            # Extract text from each page
            for page in reader.pages:
                text_content.append(page.extract_text())
            
            # Clean up temporary file
            os.unlink(temp_pdf.name)
            
            full_text = "\n".join(text_content)
            if len(full_text) > 100000:
                return full_text[:100000] + "\n[Content truncated due to length]"
            return full_text
    except Exception as e:
        return f"[Error extracting PDF content: {str(e)}]"

async def analyze_image(image_bytes):
    """Analyze image content using OCR and basic properties"""
    try:
        # Open image from bytes
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Get basic image properties
            width, height = img.size
            format_type = img.format
            mode = img.mode
            
            # Perform OCR
            text = pytesseract.image_to_string(img)
            
            # Prepare image analysis
            analysis = [
                f"Image properties:",
                f"- Dimensions: {width}x{height}",
                f"- Format: {format_type}",
                f"- Color mode: {mode}"
            ]
            
            # Add OCR results if any text was found
            if text.strip():
                analysis.append("\nExtracted text:")
                analysis.append(text.strip())
            
            return "\n".join(analysis)
    except Exception as e:
        return f"[Error analyzing image: {str(e)}]"

async def get_file_content(attachment):
    """Download and read file content from attachment with support for PDFs and images"""
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as response:
            if response.status == 200:
                file_bytes = await response.read()
                
                # Handle different file types
                if attachment.filename.lower().endswith('.pdf'):
                    return await extract_pdf_content(file_bytes)
                    
                elif any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']):
                    return await analyze_image(file_bytes)
                    
                else:
                    try:
                        # Try to decode as text for other file types
                        text_content = file_bytes.decode('utf-8')
                        if len(text_content) > 100000:
                            return text_content[:100000] + "\n[Content truncated due to length]"
                        return text_content
                    except UnicodeDecodeError:
                        return f"[Binary file: {attachment.filename}]"
            return f"[Could not access file: {attachment.filename}]"


async def format_message_history(channel, limit=25):
    """Get recent message history formatted for Claude"""
    # Check permissions first
    permissions = check_required_permissions(channel)
    missing_permissions = [perm for perm, has_perm in permissions.items() if not has_perm]
    
    if missing_permissions:
        return f"[Bot is missing required permissions: {', '.join(missing_permissions)}]"
    
    history = []
    try:
        async for message in channel.history(limit=limit):
            if message.author.bot:
                continue
                
            msg_content = f"{message.author.name}: {message.content}"
            
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in 
                          ['.txt', '.py', '.js', '.json', '.csv', '.md', '.pdf']):
                        file_content = await get_file_content(attachment)
                        msg_content += f"\nFile {attachment.filename} analysis:\n```\n{file_content}\n```"
                    else:
                        msg_content += f"\n[Attached file: {attachment.filename}]"
                    
            history.append(msg_content)
        
    except discord.Forbidden:
        return "[Error: Bot doesn't have permission to read message history. Please check bot permissions in server settings.]"
    except Exception as e:
        return f"[Error reading message history: {str(e)}]"
    
    history.reverse()
    return "\n".join(history)

@client.tree.command(name="ask", description="Ask Claude a question with context from recent messages")
async def ask(interaction: discord.Interaction, question: str):
    try:
        await interaction.response.defer()
        
        history = await format_message_history(interaction.channel)
        
        prompt = f"""Recent conversation history:
{history}

Current user {interaction.user.name} asks: {question}

Please consider the conversation history above when answering. If there are any file contents or analyses shown, you can reference and analyze them in your response."""

        message = client.anthropic.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Extract text from the response
        if hasattr(message.content, '__iter__') and not isinstance(message.content, str):
            # If content is a list of blocks, get the text from each block
            response = "\n".join(block.text for block in message.content if hasattr(block, 'text'))
        else:
            # If content is already a string
            response = str(message.content)

        # Split and send long messages
        if len(response) > 2000:
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.channel.send(chunk)
        else:
            await interaction.followup.send(response)
            
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}")


@client.tree.error
async def on_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message('You do not have the correct permissions for this command.', ephemeral=True)
    else:
        await interaction.response.send_message(f'An error occurred: {str(error)}', ephemeral=True)

def main():
    print("Starting bot...")
    print("Note: Make sure the bot has these permissions in your server:")
    print("- View Channels")
    print("- Read Message History")
    print("- Send Messages")
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()