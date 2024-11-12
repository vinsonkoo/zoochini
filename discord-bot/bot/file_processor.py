import aiohttp
import io
import os
import tempfile
from PIL import Image
from PyPDF2 import PdfReader
import pytesseract
import asyncio
from async_timeout import timeout


class FileProcessor:
    def __init__(self):
        self.config = {
            'MAX_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
            'DOWNLOAD_TIMEOUT': 30,  # seconds
            'MAX_IMAGE_PIXELS': 40000000  # 40MP
        }

    async def get_file_content(self, attachment) -> str:
        """Download and read file content from attachment with support for PDFs and images"""
        # Check file extension against whitelist first
        ext = attachment.filename.lower().split('.')[-1]
        if ext not in {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'txt'}:
            return f"[Unsupported file type: {ext}]"

        # Check MIME type
        content_type = attachment.content_type
        if not content_type or not any(content_type.startswith(t) for t in ['image/', 'application/pdf', 'text/']):
            return f"[Unsupported content type: {content_type}]"

        async with aiohttp.ClientSession() as session:
            try:
                # Add timeout for download
                async with timeout(self.config['DOWNLOAD_TIMEOUT']):
                    async with session.get(attachment.url) as response:
                        if response.status != 200:
                            return f"[Could not access file: {attachment.filename}]"

                        # Check size before downloading complete file
                        content_length = int(
                            response.headers.get('Content-Length', 0))
                        if content_length > self.config['MAX_FILE_SIZE']:
                            return f"[File too large: {attachment.filename}]"

                        file_bytes = await response.read()

                        # Process based on file type
                        if attachment.filename.lower().endswith('.pdf'):
                            # Use run_in_executor for CPU-intensive PDF processing
                            content = await asyncio.get_event_loop().run_in_executor(
                                None,
                                self._process_pdf_sync,
                                file_bytes
                            )
                            return content
                        elif any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']):
                            return await self.analyze_image(file_bytes)
                        else:
                            # Handle as text file
                            try:
                                return file_bytes.decode('utf-8')
                            except UnicodeDecodeError:
                                return "[Invalid text file encoding]"

            except asyncio.TimeoutError:
                return f"[Timeout downloading: {attachment.filename}]"
            except aiohttp.ClientError as e:
                return f"[Network error accessing file: {str(e)}]"
            except Exception as e:
                return f"[Error processing file: {str(e)}]"

    async def _is_valid_image(self, image_bytes: bytes) -> bool:
        """Quick check if bytes represent a valid image"""
        try:
            with io.BytesIO(image_bytes) as img_stream:
                with Image.open(img_stream) as img:
                    # Just load the image header
                    img.verify()
            return True
        except Exception:
            return False

    async def extract_pdf_content(self, pdf_bytes):
        """Extract text content from PDF bytes with better error handling"""
        try:
            # Create a temporary file to save PDF content
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf.write(pdf_bytes)
                temp_pdf.seek(0)
                temp_path = temp_pdf.name

            try:
                # Read PDF content with explicit error handling
                reader = PdfReader(temp_path)
                text_content = []

                if len(reader.pages) == 0:
                    return "[PDF file appears to be empty]"

                # Extract text from each page with page numbers
                for i, page in enumerate(reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text.strip():  # Only add non-empty pages
                        text_content.append(
                            f"--- Page {i} ---\n{page_text.strip()}")

                # Clean up temporary file
                os.unlink(temp_path)

                if not text_content:
                    return "[PDF file contains no extractable text - it may be scanned or image-based]"

                full_text = "\n\n".join(text_content)
                if len(full_text) > 100000:
                    return full_text[:100000] + "\n[Content truncated due to length]"
                return full_text

            except Exception as e:
                # Clean up temp file if PDF processing fails
                os.unlink(temp_path)
                raise

        except Exception as e:
            return f"[Error extracting PDF content: {str(e)}]"

    async def analyze_image(self, image_bytes: bytes) -> str:
        """Analyze image content using OCR and basic properties"""
        if len(image_bytes) > self.config['MAX_FILE_SIZE']:
            return "[Image too large for analysis]"

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size
                if width * height > self.config['MAX_IMAGE_PIXELS']:
                    return "[Image dimensions too large for processing]"

                # Run OCR in threadpool
                text = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: pytesseract.image_to_string(img)
                )

                if not text.strip():
                    return "[No text detected in image]"

                return text.strip()

        except Exception as e:
            return f"[Error analyzing image: {str(e)}]"

    async def process_text_file(self, file_bytes, filename):
        try:
            text_content = file_bytes.decode('utf-8')
            if len(text_content) > 100000:
                return text_content[:100000] + "\n[Content truncated due to length]"
            return text_content
        except UnicodeDecodeError:
            return f"[Binary file: {filename}]"

    def _process_pdf_sync(self, pdf_bytes: bytes) -> str:
        """Synchronously process PDF content - meant to be run in executor"""
        try:
            # Create a temporary file to save PDF content
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf.write(pdf_bytes)
                temp_pdf.seek(0)
                temp_path = temp_pdf.name

            try:
                # Read PDF content
                reader = PdfReader(temp_pdf.name)
                text_content = []

                if len(reader.pages) == 0:
                    return "[PDF file appears to be empty]"

                # Extract text from each page
                for i, page in enumerate(reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_content.append(f"[Page {i}]\n{page_text.strip()}")

                if not text_content:
                    # If no text was extracted, PDF might be scanned
                    return "[This appears to be a scanned PDF - no extractable text found]"

                # Join all pages with clear separation
                full_text = "\n\n".join(text_content)

                # Truncate if too long
                if len(full_text) > 100000:
                    return full_text[:100000] + "\n[Content truncated due to length]"

                return full_text

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            return f"[Error reading PDF: {str(e)}]"
