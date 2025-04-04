import aiohttp
import asyncio
import discord
from async_timeout import timeout
from .claude_client import ClaudeClient
from .file_processor import FileProcessor
from .drive_processor import DriveProcessor


class MessageHandler:
    def __init__(self, claude_client: ClaudeClient, file_processor: FileProcessor, drive_processor: DriveProcessor):
        self.claude_client = claude_client
        self.file_processor = file_processor
        self.drive_processor = drive_processor
        self.aiohttp_session = None

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
        permissions = self._check_required_permissions(channel)
        missing_permissions = [perm for perm,
                               has_perm in permissions.items() if not has_perm]

        if missing_permissions:
            return f"[Bot is missing required permissions: {', '.join(missing_permissions)}]"

        try:
            async with timeout(30):
                history = []
                async for message in channel.history(limit=limit):
                    if message.author.bot:
                        continue

                    # Build the basic message content
                    msg_parts = []
                    msg_parts.append(
                        f"[{message.created_at.isoformat()}] {message.author.name}")

                    if message.reference and hasattr(message.reference, 'resolved') and message.reference.resolved:
                        msg_parts.append(
                            f"(replying to {message.reference.resolved.author.name})")

                    # Add the message text if it exists
                    if message.content:
                        msg_parts.append(f": {message.content}")

                    # Process attachments if they exist
                    if message.attachments:
                        for attachment in message.attachments:
                            try:
                                async with timeout(10):
                                    content = await self.file_processor.get_file_content(attachment)
                                    if content and content.strip():
                                        # Format attachment content in a clear structure
                                        msg_parts.append(
                                            "\n=== Begin Attachment Content ===")
                                        msg_parts.append(
                                            f"Filename: {attachment.filename}")
                                        msg_parts.append(
                                            f"Content type: {attachment.content_type}")
                                        msg_parts.append("Content:")
                                        msg_parts.append(content.strip())
                                        msg_parts.append(
                                            "=== End Attachment Content ===\n")
                            except asyncio.TimeoutError:
                                msg_parts.append(
                                    f"\n[Timeout processing attachment: {attachment.filename}]")
                            except Exception as e:
                                msg_parts.append(
                                    f"\n[Error processing attachment {attachment.filename}: {str(e)}]")

                    # Join all parts of the message
                    history.append(" ".join(msg_parts))

        except discord.Forbidden:
            return "[Error: Bot doesn't have permission to read message history]"
        except asyncio.TimeoutError:
            return "[Error: Timeout while retrieving message history]"
        except Exception as e:
            return f"[Error reading message history: {str(e)}]"

        history.reverse()
        formatted_history = "\n".join(history)

        # Add a clear header to help Claude understand the context
        return f"""This is a Discord chat history with attachments. Each message shows its timestamp, author, and content. 
Attachments are clearly marked between === Begin Attachment Content === and === End Attachment Content === markers.

{formatted_history}"""

    async def handle_ask_command(self, interaction: discord.Interaction, question: str, file: discord.Attachment = None):
        try:
            await interaction.response.defer()

            # Get message history
            history = await self.format_message_history(interaction.channel)

            # Process file if provided
            file_content = ""

            # Handle both pasted images (which become embedded URLs) and file attachments
            if file:
                if file.content_type and file.content_type.startswith('image/'):
                    # Create session if needed
                    if not self.aiohttp_session:
                        self.aiohttp_session = aiohttp.ClientSession()

                    async with self.aiohttp_session.get(file.url) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            file_content = await self.file_processor.analyze_image(image_bytes)
                else:
                    # Handle as normal file attachment
                    file_content = await self.file_processor.get_file_content(file)

                if file_content:
                    file_content = f"\nFile attachment ({file.filename}) content:\n{file_content}"

            # Combine question with file content if present
            full_question = question
            if file_content:
                full_question = f"{question}\n\nAnalyze this attached file: {file_content}"

            # Get Claude's response
            response = await self.claude_client.get_response(interaction.user.name, full_question, history)
            await self._send_chunked_response(interaction, response)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")
            raise  # Re-raise to see full traceback in logs

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

    async def handle_ask_drive_command(self, interaction: discord.Interaction, doc_id: str, question: str):
        try:
            await interaction.response.defer()

            # Get document content
            doc_content = await self.drive_processor.get_document_content(doc_id)

            # Format prompt with document content
            prompt = f"""Document content: {doc_content}\n\nQuestion: {question}"""

            # Get Claude's response
            response = await self.claude_client.get_response(interaction.user.name, prompt, "")

            await self._send_chunked_response(interaction, response)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    async def handle_list_folder_command(self, interaction: discord.Interaction, folder_id: str):
        try:
            await interaction.response.defer()
            files = await self.drive_processor.list_folder_contents(folder_id)

            if not files:
                await interaction.followup.send("No files found in this folder.")
                return

            response = "Files in folder:\n"
            for file in files:
                response += f"- {file['name']} (ID: {file['id']})\n"

            await self._send_chunked_response(interaction, response)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    async def handle_ask_folder_command(self, interaction: discord.Interaction, folder_id: str, question: str):
        try:
            await interaction.response.defer()

            # Get files listing regardless of question
            files = await self.drive_processor.list_folder_contents(folder_id)

            # Always prepare the file listing
            listing = "Contents of this folder:\n\n=== FOLDERS ===\n"
            folders = [f for f in files if f['type'] ==
                       'application/vnd.google-apps.folder']
            if folders:
                for folder in folders:
                    listing += f"📁 {folder['name']}\n   ID: {folder['id']}\n"
            else:
                listing += "(No subfolders)\n"

            listing += "\n=== FILES ===\n"
            regular_files = [f for f in files if f['type']
                             != 'application/vnd.google-apps.folder']
            if regular_files:
                for file in regular_files:
                    icon = self._get_file_icon(file['type'])
                    listing += f"{icon} {file['name']}\n   ID: {file['id']}\n"
            else:
                listing += "(No files)\n"

            # If only asking for listing, return just that
            if any(keyword in question.lower() for keyword in ['list', 'what files', 'show files']) and len(question.split()) <= 4:
                await self._send_chunked_response(interaction, listing)
                return

            # If there's a more complex question, get content analysis and combine with listing
            folder_content = await self.drive_processor.get_folder_content(folder_id)
            prompt = f"""File listing of the folder:
                {listing}

                Folder contents:
                {folder_content}

                Question: {question}

                Please start your response by showing the file listing above, then answer the question about the contents."""

            response = await self.claude_client.get_response(interaction.user.name, prompt, "")
            await self._send_chunked_response(interaction, response)

        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    def _get_file_icon(self, mime_type: str) -> str:
        """Get an appropriate emoji icon for the file type"""
        if mime_type == 'application/vnd.google-apps.document':
            return "📄"  # Google Doc
        elif mime_type == 'application/pdf':
            return "📕"  # PDF
        elif mime_type.startswith('image/'):
            return "🖼️"  # Image
        elif mime_type.startswith('text/'):
            return "📝"  # Text
        elif mime_type.startswith('audio/'):
            return "🎵"  # Audio
        elif mime_type.startswith('video/'):
            return "🎥"  # Video
        elif mime_type.startswith('application/vnd.google-apps.spreadsheet'):
            return "📊"  # Spreadsheet
        elif mime_type.startswith('application/vnd.google-apps.presentation'):
            return "📎"  # Presentation
        else:
            return "📎"  # Generic file

    async def handle_search_drive_command(self, interaction: discord.Interaction, name: str, type: str = None):
        try:
            await interaction.response.defer()

            if type and type.lower() not in ['folder', 'document']:
                await interaction.followup.send("Type must be either 'folder' or 'document' if specified.")
                return

            files = await self.drive_processor.search_files(name, type.lower() if type else None)

            if not files:
                await interaction.followup.send(f"No {'files' if type != 'folder' else 'folders'} found matching '{name}'")
                return

            response = f"Found {len(files)} items matching '{name}':\n"
            for file in files:
                response += f"- {file['name']} ({file['type']}) in {file['parent']}\n  ID: {file['id']}\n"

            await self._send_chunked_response(interaction, response)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    async def handle_ask_about_command(self, interaction: discord.Interaction, name: str, question: str):
        try:
            await interaction.response.defer()

            # Search for matching files
            files = await self.drive_processor.search_files(name, 'document')

            if not files:
                await interaction.followup.send(f"No files found matching '{name}'")
                return

            # Get content for each matching file
            all_content = []
            for file in files[:5]:  # Limit to first 5 matches to avoid overload
                content = await self.drive_processor.get_document_content(file['id'])
                all_content.append(f"=== {file['name']} ===\n{content}\n")

            # Format prompt with all file contents
            prompt = f"""Found {len(files)} files matching '{name}'. Content of first 5 files:\n\n"""
            prompt += "\n".join(all_content)
            prompt += f"\n\nQuestion: {question}"

            # Get Claude's response
            response = await self.claude_client.get_response(interaction.user.name, prompt, "")

            await self._send_chunked_response(interaction, response)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

    async def cleanup(self):
        """Cleanup method to close the aiohttp session"""
        if self.aiohttp_session:
            await self.aiohttp_session.close()
            self.aiohttp_session = None
