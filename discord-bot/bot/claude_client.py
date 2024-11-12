import asyncio
from asyncio import Lock
from anthropic import Anthropic
from datetime import datetime, timedelta
from typing import Optional, ClassVar


class ClaudeClient:
    _global_lock: ClassVar[Lock] = Lock()
    _last_call: ClassVar[Optional[datetime]] = None

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.last_call = None
        self.RATE_LIMIT = 0.5  # seconds between calls

    async def get_response(self, username: str, question: str, history: str) -> Optional[str]:
        async with self._global_lock:  # Global rate limiting
            now = datetime.now()
            if self._last_call:
                time_since_last = now - self._last_call
                if time_since_last < timedelta(seconds=self.RATE_LIMIT):
                    await asyncio.sleep(self.RATE_LIMIT - time_since_last.total_seconds())

            for attempt in range(3):
                try:
                    prompt = f"""Recent conversation history: {history}
                    Current user {username} asks: {question}
                    Please consider the conversation history above when answering."""

                    # Run API call in threadpool to avoid blocking
                    message = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.client.messages.create(
                            model="claude-3-5-sonnet-latest",
                            max_tokens=4000,
                            messages=[{"role": "user", "content": prompt}]
                        )
                    )

                    self.last_call = datetime.now()

                    if not message.content:
                        return None

                    return message.content[0].text

                except Exception as e:
                    print(f"Claude API error: {str(e)}")
                    return None
