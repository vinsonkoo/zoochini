# Zoochini

A Discord bot that integrates Claude AI with Discord and Google Drive, enabling intelligent document analysis and conversation capabilities within Discord channels.

## Project Overview

Zoochini is a powerful Discord bot that combines Discord's messaging capabilities with Anthropic's Claude AI to create an intelligent assistant that can analyze documents, images, and conversations. The bot provides seamless access to Claude's powerful language capabilities directly within Discord channels, and extends functionality to include Google Drive integration for working with documents stored in the cloud.

Key capabilities include:
- Answering questions based on conversation context
- Processing and analyzing various file types (PDFs, images, text files)
- Extracting text from images using OCR
- Integrating with Google Drive to access and analyze cloud documents
- Providing a natural language interface to search and retrieve information

## Technology Stack

- **Python 3.13+**: Core programming language
- **Discord.py 2.4.0**: Framework for Discord bot functionality
- **Anthropic API**: Integration with Claude 3.5 Sonnet model for AI capabilities
- **Google Drive API**: For document storage and retrieval
- **Tesseract OCR**: For extracting text from images
- **PyPDF2**: For PDF document processing
- **Docker**: For containerization and deployment
- **Google Cloud Build**: For CI/CD pipeline

## Core Features

1. **Intelligent Conversation**
   - Context-aware responses using Claude AI
   - Message history analysis for maintaining conversation context
   - Rate-limiting to prevent API abuse

2. **File Analysis**
   - Support for multiple file types (PDFs, images, text)
   - OCR capabilities for extracting text from images
   - PDF parsing for document analysis

3. **Google Drive Integration**
   - Search and access Google Drive documents
   - List folder contents
   - Process and analyze Google Docs, PDFs, and images from Drive
   - Ask questions about documents stored in Drive

4. **Discord Commands**
   - `/ask`: Ask Claude a question with optional file attachment
   - `/ask_drive`: Ask questions about specific Google Drive documents
   - `/list_folder`: List contents of a Google Drive folder
   - `/ask_folder`: Ask questions about all documents in a folder
   - `/search_drive`: Search for files or folders by name
   - `/ask_about`: Ask questions about files matching a specific name

5. **Security and Permissions**
   - OAuth2 authentication for secure Google Drive access
   - Permission checks for Discord operations
   - Credential management for API access
