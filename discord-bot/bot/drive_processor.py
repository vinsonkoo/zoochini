from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pathlib import Path
import io
import os
import pickle
import tempfile
import os
from PIL import Image
import pytesseract
from PyPDF2 import PdfReader
from asyncio import Lock
import async_timeout


class DriveProcessor:
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

    def __init__(self, credentials_dir: str = None):
        # Config settings for limits and timeouts
        self.config = {
            'MAX_CONTENT_LENGTH': 100000,
            'TIMEOUT_SECONDS': 30,
            'MAX_FILE_SIZE': 10 * 1024 * 1024  # 10MB
        }

        # If no credentials_dir provided, use parent directory of bot folder
        if credentials_dir is None:
            # Get bot directory (where this file is)
            bot_dir = Path(__file__).resolve().parent
            # Go up one level and into credentials
            self.creds_dir = bot_dir.parent / 'credentials'
        else:
            self.creds_dir = Path(credentials_dir)

        # Ensure credentials directory exists
        self.creds_dir.mkdir(exist_ok=True)

        # Set paths
        self.credentials_path = self.creds_dir / 'google_credentials.json'
        self.token_path = self.creds_dir / 'token.pickle'
        self.service = None

        # Verify credentials.json exists
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"credentials.json not found in {self.creds_dir}. "
                "Please download it from Google Cloud Console and place it in the credentials directory."
            )

        # Add lock for concurrent authentication
        self._auth_lock = Lock()
        self._max_retries = 3

    async def authenticate(self):
        async with self._auth_lock:  # Prevent concurrent auth attempts
            for attempt in range(self._max_retries):
                try:
                    async with async_timeout.timeout(self.config['TIMEOUT_SECONDS']):
                        creds = None

                        # Keep your existing token loading
                        if self.token_path.exists():
                            try:
                                with open(self.token_path, 'rb') as token:
                                    creds = pickle.load(token)
                            except Exception as e:
                                print(f"Error loading token: {e}")
                                self.token_path.unlink(missing_ok=True)

                        # Keep your existing credential refresh/creation logic
                        if not creds or not creds.valid:
                            if creds and creds.expired and creds.refresh_token:
                                print("Refreshing expired token...")
                                await asyncio.get_event_loop().run_in_executor(
                                    None,
                                    lambda: creds.refresh(Request())
                                )
                            else:
                                print("Getting new token...")
                                flow = await asyncio.get_event_loop().run_in_executor(
                                    None,
                                    lambda: InstalledAppFlow.from_client_secrets_file(
                                        str(self.credentials_path),
                                        self.SCOPES
                                    )
                                )
                                creds = await asyncio.get_event_loop().run_in_executor(
                                    None,
                                    lambda: flow.run_local_server(port=0)
                                )

                            # Keep token saving
                            with open(self.token_path, 'wb') as token:
                                pickle.dump(creds, token)
                            print(f"Token saved to {self.token_path}")

                        # Keep service building
                        self.service = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: build('drive', 'v3', credentials=creds)
                        )
                        return  # Success!

                except asyncio.TimeoutError:
                    if attempt == self._max_retries - 1:
                        raise
                    await asyncio.sleep(1)  # Wait before retry
                except Exception as e:
                    if attempt == self._max_retries - 1:
                        raise
                    print(f"Auth attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(1)

    async def search_files(self, query_name: str, file_type: str = None) -> list:
        """Search for files/folders by name"""
        if not self.service:
            self.authenticate()

        try:
            query_parts = [f"name contains '{query_name}' and trashed = false"]

            if file_type == 'folder':
                query_parts.append(
                    "mimeType = 'application/vnd.google-apps.folder'")
            elif file_type == 'document':
                query_parts.append(
                    "mimeType != 'application/vnd.google-apps.folder'")

            query = " and ".join(query_parts)

            results = []
            page_token = None

            while True:
                files = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, parents)',
                    pageToken=page_token
                ).execute()

                for file in files.get('files', []):
                    # Get parent folder name if possible
                    parent_name = "Root"
                    if file.get('parents'):
                        try:
                            parent = self.service.files().get(
                                fileId=file['parents'][0],
                                fields='name'
                            ).execute()
                            parent_name = parent['name']
                        except:
                            pass

                    results.append({
                        'id': file['id'],
                        'name': file['name'],
                        'type': 'Folder' if file['mimeType'] == 'application/vnd.google-apps.folder' else 'File',
                        'parent': parent_name
                    })

                page_token = files.get('nextPageToken')
                if not page_token:
                    break

            return results

        except Exception as e:
            print(f"Error searching files: {str(e)}")
            return []

    async def list_folder_contents(self, folder_id: str) -> list:
        """List all files in a folder"""
        if not self.service:
            self.authenticate()

        try:
            results = []
            page_token = None

            while True:
                # Query for files in the specified folder
                query = f"'{folder_id}' in parents and trashed = false"
                files = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType)',
                    pageToken=page_token
                ).execute()

                for file in files.get('files', []):
                    results.append({
                        'id': file['id'],
                        'name': file['name'],
                        'type': file['mimeType']
                    })

                page_token = files.get('nextPageToken')
                if not page_token:
                    break

            return results

        except Exception as e:
            print(f"Error listing folder contents: {str(e)}")
            return []

    async def get_folder_content(self, folder_id: str) -> str:
        """Get content of files in a folder, with folder summary at the top"""
        try:
            files = await self.list_folder_contents(folder_id)

            # First create a summary of folders
            folder_summary = []
            folder_summary.append("=== FOLDERS IN THIS DIRECTORY ===")
            folders = [f for f in files if f['type'] ==
                       'application/vnd.google-apps.folder']
            if folders:
                for folder in folders:
                    folder_summary.append(
                        f"- {folder['name']} (ID: {folder['id']})")
            else:
                folder_summary.append("(No subfolders)")
            folder_summary.append("\n=== FILE CONTENTS ===")

            # Then process file contents
            all_content = []
            for file in files:
                mime_type = file['type']

                if mime_type != 'application/vnd.google-apps.folder':  # Skip folders as they're already listed
                    content = await self.get_document_content(file['id'])
                    all_content.append(f"=== {file['name']} ===\n{content}\n")

            # Combine folder summary with file contents
            combined_content = "\n".join(folder_summary + all_content)
            if len(combined_content) > 100000:
                return combined_content[:100000] + "\n[Content truncated due to length]"
            return combined_content

        except Exception as e:
            return f"[Error accessing folder contents: {str(e)}]"

    async def get_document_content(self, file_id: str) -> str:
        """Download and extract content from a Google Drive document"""
        if not self.service:
            await self.authenticate()

        temp_files = []  # Track temporary files for cleanup
        try:
            # Get file metadata to check mime type
            file = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.service.files().get(fileId=file_id, fields='mimeType, name').execute()
            )
            mime_type = file.get('mimeType', '')
            file_name = file.get('name', '')

            # Handle different types of files
            if mime_type == 'application/vnd.google-apps.document':
                # Export Google Docs as plain text
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.service.files().export(
                        fileId=file_id,
                        mimeType='text/plain'
                    ).execute()
                )
                content = response.decode('utf-8')

            elif mime_type == 'application/pdf':
                content = await self._process_pdf_file(file_id, temp_files)

            elif mime_type.startswith('image/'):
                content = await self._process_image_file(file_id)

            elif mime_type.startswith('text/'):
                content = await self._process_text_file(file_id)

            else:
                return f"[Unsupported file type: {mime_type}]"

            # Truncate if too long
            if len(content) > self.config['MAX_CONTENT_LENGTH']:
                return content[:self.config['MAX_CONTENT_LENGTH']] + "\n[Content truncated due to length]"
            return content

        except Exception as e:
            return f"[Error reading {file_name}: {str(e)}]"
        finally:
            # Clean up any temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except Exception as e:
                    print(f"Error cleaning up temporary file {temp_file}: {e}")

    async def _process_pdf_file(self, file_id: str, temp_files: list) -> str:
        # Download PDF and extract text
        request = self.service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)

        # Download in chunks
        done = False
        while not done:
            _, done = await asyncio.get_event_loop().run_in_executor(
                None,
                downloader.next_chunk
            )

        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            temp_pdf.write(file_content.getvalue())
            temp_pdf.seek(0)
            temp_files.append(temp_pdf.name)  # Add to cleanup list

            # Extract text using PyPDF2
            reader = PdfReader(temp_pdf.name)
            content_parts = []

            for page in reader.pages:
                content_parts.append(page.extract_text())

            return "\n".join(content_parts)

    async def _process_image_file(self, file_id: str) -> str:
        # Handle images using OCR
        request = self.service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)

        # Download in chunks
        done = False
        while not done:
            _, done = await asyncio.get_event_loop().run_in_executor(
                None,
                downloader.next_chunk
            )

        # Use PIL and pytesseract for OCR
        with Image.open(file_content) as img:
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: pytesseract.image_to_string(img)
            )

        if not content.strip():
            return "[Image file - no text detected]"
        return content

    async def _process_text_file(self, file_id: str) -> str:
        # Handle plain text files
        request = self.service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)

        # Download in chunks
        done = False
        while not done:
            _, done = await asyncio.get_event_loop().run_in_executor(
                None,
                downloader.next_chunk
            )

        return file_content.getvalue().decode('utf-8')
