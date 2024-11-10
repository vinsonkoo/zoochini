import aiohttp
import io
import os
import tempfile
from PIL import Image
from PyPDF2 import PdfReader
import pytesseract


class FileProcessor:
    async def get_file_content(self, attachment):
        """Download and read file content from attachment with support for PDFs and images"""
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as response:
                if response.status == 200:
                    file_bytes = await response.read()

                    # Handle different file types
                    if attachment.filename.lower().endswith('.pdf'):
                        return await self.extract_pdf_content(file_bytes)

                    elif any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']):
                        return await self.analyze_image(file_bytes)

                    else:
                        return await self.process_text_file(file_bytes, attachment.filename)
                return f"[Could not access file: {attachment.filename}]"

    async def extract_pdf_content(self, pdf_bytes):
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

    async def analyze_image(self, image_bytes):
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

    async def process_text_file(self, file_bytes, filename):
        try:
            text_content = file_bytes.decode('utf-8')
            if len(text_content) > 100000:
                return text_content[:100000] + "\n[Content truncated due to length]"
            return text_content
        except UnicodeDecodeError:
            return f"[Binary file: {filename}]"
