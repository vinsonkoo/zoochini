import asyncio
import discord
from .claude_client import ClaudeClient
from .file_processor import FileProcessor


class MessageHandler:
    def __init__(self, claude_client: ClaudeClient, file_processor: FileProcessor):
        self.claude_client = claude_client
        self.file_processor = file_processor

    def _check_required_permissions(self, channel):
        """Check if bot has required permissions in the channel"""
        if not isinstance(channel, discord.TextChannel):
            return {'view_channel': False, 'read_message_history': False, 'send_messages': False}

        permissions = channel.permissions_for(channel.guild.me)
        return {
            'view_channel': permissions.view_channel,
            'read_message_history': permissions.read_message_history,
            'send_messages': permissions.send_messages
        }

    async def format_message_history(self, channel, limit=25):
        """Get recent message history formatted for Claude"""
        # Check permissions first
        permissions = self._check_required_permissions(channel)
        missing_permissions = [perm for perm,
                               has_perm in permissions.items() if not has_perm]

        if missing_permissions:
            return f"[Bot is missing required permissions: {', '.join(missing_permissions)}]"

        history = []
        try:
            async for message in channel.history(limit=limit):
                if message.author.bot:
                    continue

                # Add timestamp and reply info
                msg_content = f"[{message.created_at.isoformat()}] {message.author.name}"
                if message.reference and message.reference.resolved:
                    msg_content += f" (replying to {message.reference.resolved.author.name})"
                msg_content += f": {message.content}"

                # Process attachments concurrently
                if message.attachments:
                    tasks = [self.file_processor.get_file_content(attachment)
                             for attachment in message.attachments]
                    contents = await asyncio.gather(*tasks)
                    for attachment, content in zip(message.attachments, contents):
                        msg_content += f"\nFile {attachment.filename}:\n{content}\n"

                history.append(msg_content)

        except discord.Forbidden:
            return "[Error: Bot doesn't have permission to read message history. Please check bot permissions in server settings.]"
        except Exception as e:
            return f"[Error reading message history: {str(e)}]"

        history.reverse()
        return "\n".join(history)

    async def handle_ask_command(self, interaction: discord.Interaction, question: str):
        try:
            await interaction.response.defer()
            history = await self.format_message_history(interaction.channel)
            response = await self.claude_client.get_response(interaction.user.name, question, history)
            await self._send_chunked_response(interaction, response)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    async def _send_chunked_response(self, interaction, response: str):
        # Handle Discord's 2000 character limit
        if len(response) <= 1900:
            await interaction.followup.send(response)
            return

        # Split into chunks of approximately 1900 characters
        chunks = []
        current_chunk = []
        current_length = 0

        # Split on sentences
        sentences = [s.strip() + '.' for s in response.split('.') if s.strip()]

        for sentence in sentences:
            if current_length + len(sentence) > 1900:
                # Send current chunk
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1  # +1 for space

        # Add any remaining content
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        # Send all chunks
        for chunk in chunks:
            await interaction.followup.send(chunk)
