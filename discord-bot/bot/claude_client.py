# bot/claude_client.py
from anthropic import Anthropic


class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    async def get_response(self, username: str, question: str, history: str) -> str:
        prompt = f"""Recent conversation history: {history}
        Current user {username} asks: {question}
        Please consider the conversation history above when answering. If there are any file contents or analyses shown, you can reference and analyze them in your response."""

        message = self.client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        # Extract the text content from the message
        return message.content[0].text
