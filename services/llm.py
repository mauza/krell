"""
LLM Service - OpenAI-compatible API for chat generation.
"""

from typing import Optional, List, Dict, AsyncGenerator
from openai import OpenAI, AsyncOpenAI


class LLMService:
    def __init__(
        self,
        model: str,
        endpoint: str,
        openai_api_key: Optional[str] = None,
    ):
        self.model = model
        self.endpoint = endpoint.rstrip("/") if endpoint else ""

        # Initialize OpenAI clients with custom endpoint if provided
        client_args = {"api_key": openai_api_key}
        if self.endpoint and self.endpoint != "https://api.openai.com":
            client_args["base_url"] = self.endpoint

        self.openai_client = OpenAI(**client_args) if openai_api_key else None
        self.async_openai_client = (
            AsyncOpenAI(**client_args) if openai_api_key else None
        )

    async def generate_response(self, user_message: str, context: str = "") -> str:
        system_prompt = (
            "You are Krell, a helpful AI companion. You have access to past conversations for context.\n\n"
            + ("Previous conversations:\n" + context + "\n\n" if context else "")
            + "Use this context to provide personalized and relevant responses. Be conversational, friendly and witty. "
            + "Keep responses short and concise. No one likes a chatty Cathy."
        )

        if not self.openai_client:
            raise Exception("OpenAI API key not set.")

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            raise Exception(f"Failed to call OpenAI-compatible API: {e}")

    async def generate_streaming_response(
        self, user_message: str, context: str = ""
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response from LLM."""
        system_prompt = (
            "You are Krell, a helpful AI companion. You have access to past conversations for context.\n\n"
            + ("Previous conversations:\n" + context + "\n\n" if context else "")
            + "Use this context to provide personalized and relevant responses. Be conversational, friendly and witty. "
            + "Keep responses short and concise. No one likes a chatty Cathy."
        )

        if not self.async_openai_client:
            raise Exception("OpenAI API key not set.")

        try:
            response = await self.async_openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                stream=True,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            raise Exception(f"Failed to call OpenAI-compatible API: {e}")
