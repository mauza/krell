"""
Krell Agent - Strands agent integration with OpenAI-compatible LLM

This module wraps the Strands agent framework to provide Krell's conversational AI
capabilities, including:
- Loading LLM configuration from database settings
- Managing conversation history with context limits
- Tool calling support for autonomous actions
- Journal entry creation
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
import json
import logging
import os
from database.db import Database
from strands import Agent
from strands.models.openai import OpenAIModel

# Set up logging
logger = logging.getLogger(__name__)


class KrellAgent:
    """
    Krell agent implementation using Strands framework.

    Loads configuration from database and manages conversation context.
    """

    # Default system prompt
    SYSTEM_PROMPT = """You are a personal information assistant and life scribe. Your primary purpose is to help capture, organize, and recall information about the user's life.

Keep responses concise and direct. Aim for clarity over length.

Your core responsibilities:
1. Capture information about people, places, things, events, and experiences
2. Help retrieve and connect information when asked
3. Proactively suggest recording important moments or ratings when appropriate

When you detect:
- New people, places, or things being mentioned → Create entities to track them
- Experiences with positive/negative sentiment → Ask if they'd like to rate it (1-5)
- Important events or moments → Offer to create journal entries
- Mentions of previously tracked entities with missing details → Occasionally ask for more context

Probing behavior:
- When entities are mentioned again and have missing details, ask once for clarification
- When you detect strong sentiment about experiences, suggest rating them
- Keep probes natural and contextual - don't interrupt the conversation flow
- If they decline or ignore a probe, don't ask again for that specific detail

When retrieving information:
- Present findings conversationally with source references
- Offer to drill down into related details
- Connect related information (people at events, rated experiences, etc.)

You are a scribe and memory keeper, not a conversational companion. Focus on being helpful through information management."""

    def __init__(
        self,
        db: Database,
        llm_endpoint: str,
        llm_model: str,
        context_limit: int = 20,
        system_prompt: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        """
        Initialize Krell agent.

        Args:
            db: Database instance for storing conversations
            llm_endpoint: LLM API endpoint URL (OpenAI-compatible)
            llm_model: Model name to use
            context_limit: Maximum number of messages to include in context
            system_prompt: Override default system prompt
            openai_api_key: OpenAI API key (optional, will use env var if not provided)
        """
        self.db = db
        self.llm_endpoint = llm_endpoint
        self.llm_model = llm_model
        self.context_limit = context_limit
        self.system_prompt = system_prompt or self.SYSTEM_PROMPT

        # Initialize OpenAI model with API key and endpoint
        # For local LLMs like Ollama, API key may not be required
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "dummy-key")

        client_args = {"api_key": api_key}
        if llm_endpoint and llm_endpoint != "https://api.openai.com":
            # Ensure Ollama endpoints have /v1 suffix for OpenAI compatibility
            base_url = llm_endpoint
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"
            client_args["base_url"] = base_url

        self._model = OpenAIModel(
            client_args=client_args,
            model_id=llm_model,
        )

        # Create the agent (no tools yet - will be added in plugin system)
        self._strands_agent = Agent(
            model=self._model,
            system_prompt=self.system_prompt,
            tools=[],  # Tools will be added by plugin loader
        )

        logger.info(
            f"Initialized KrellAgent with model={llm_model}, endpoint={llm_endpoint}"
        )

    @classmethod
    async def create(
        cls,
        db: Database,
        context_limit: int = 20,
        system_prompt: Optional[str] = None,
    ) -> "KrellAgent":
        """
        Create a KrellAgent by loading configuration from database.

        Args:
            db: Database instance
            context_limit: Maximum number of messages in context
            system_prompt: Override default system prompt

        Returns:
            Initialized KrellAgent
        """
        # Load settings from database
        llm_endpoint = await db.get_setting("llm_endpoint")
        llm_model = await db.get_setting("llm_model")
        openai_api_key = await db.get_setting("api_key", decrypt=True)

        # Debug logging
        logger.info(
            f"Loaded settings - endpoint: {llm_endpoint}, model: {llm_model}, api_key: {'set' if openai_api_key else 'not set'}"
        )

        # Use defaults if not set
        if not llm_endpoint:
            llm_endpoint = "https://api.openai.com"
        if not llm_model:
            llm_model = "gpt-4o-mini"
        if not openai_api_key:
            openai_api_key = os.getenv("OPENAI_API_KEY", "")
            logger.info(
                f"Falling back to env var API key: {'set' if openai_api_key else 'not set'}"
            )

        return cls(
            db=db,
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            context_limit=context_limit,
            system_prompt=system_prompt,
            openai_api_key=openai_api_key,
        )

    async def load_conversation_history(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        Load conversation history from database.

        Respects context_limit to avoid overwhelming the LLM.

        Args:
            conversation_id: ID of conversation to load

        Returns:
            List of message dictionaries with role and content
        """
        # Get all messages for conversation
        messages = await self.db.get_conversation_messages(conversation_id)

        # Apply context limit - keep only last N messages
        if len(messages) > self.context_limit:
            messages = messages[-self.context_limit :]

        # Convert to format expected by Strands
        # Strands expects a list of Message TypedDict:
        # Message = {"role": Literal["user", "assistant"], "content": List[ContentBlock]}
        # ContentBlock can have "text" field for simple text
        formatted_messages = []
        for msg in messages:
            formatted_messages.append(
                {
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}],
                }
            )

        return formatted_messages

    async def chat(
        self,
        conversation_id: Optional[str],
        user_message: str,
    ) -> Dict[str, Any]:
        """
        Generate a response to user message.

        Args:
            conversation_id: Conversation ID, or None to create new
            user_message: User's message text

        Returns:
            Dict with:
                - response: Agent's text response
                - conversation_id: ID of conversation
                - tool_calls: List of tool calls made (if any)
        """
        # Create new conversation if needed
        if conversation_id is None:
            conversation_id = await self.db.create_conversation(
                "New Conversation"  # Will be updated with generated title later
            )

        # Load conversation history
        history = await self.load_conversation_history(conversation_id)

        # Save user message to database
        await self.db.add_message(conversation_id, "user", user_message)

        logger.info(
            f"Processing chat request for conversation {conversation_id}: '{user_message[:50]}...'"
        )

        try:
            # Call the Strands agent with conversation history
            # Strands API: agent(prompt, **kwargs) where prompt can be:
            # - str: simple text
            # - list[ContentBlock]: multi-modal content
            # - list[Message]: complete message history
            #
            # When we pass list[Message], it includes the full conversation.
            # We need to append the user's new message to the history.
            messages_with_new = history + [
                {
                    "role": "user",
                    "content": [{"text": user_message}],
                }
            ]

            # Invoke the agent with full conversation history
            result = self._strands_agent(messages_with_new)

            # Handle different return types (for testing vs production)
            response_text = ""
            tool_calls = []

            # Check if this is a mock returning a simple string
            if isinstance(result, str):
                response_text = result
            # Check if this is a mock object with response/tool_calls attributes
            elif hasattr(result, "response"):
                response_text = result.response
                if hasattr(result, "tool_calls"):
                    tool_calls = result.tool_calls
            # Otherwise, treat as real AgentResult
            elif hasattr(result, "message"):
                # Extract response text from AgentResult
                # result.message is a Message TypedDict: {"role": str, "content": List[ContentBlock]}
                # ContentBlock can have "text", "toolUse", "toolResult", etc.
                for block in result.message["content"]:
                    if "text" in block:
                        response_text += block["text"]
                    elif "toolUse" in block:
                        # Extract tool call information
                        tool_use = block["toolUse"]
                        tool_calls.append(
                            {
                                "id": tool_use["toolUseId"],
                                "name": tool_use["name"],
                                "input": tool_use["input"],
                            }
                        )

            logger.info(f"Agent response: '{response_text[:50]}...'")
            if tool_calls:
                try:
                    # Try to log tool names if available
                    tool_names = [
                        tc.get("name", tc.get("tool", "unknown")) for tc in tool_calls
                    ]
                    logger.info(f"Tool calls made: {tool_names}")
                except (TypeError, AttributeError):
                    logger.info(f"Tool calls made: {len(tool_calls)} calls")

        except Exception as e:
            logger.error(f"Error during agent invocation: {e}", exc_info=True)
            response_text = "I apologize, but I encountered an error processing your message. Please try again."
            tool_calls = []

        # Save agent response to database
        # Only save tool_calls if they're actual dicts, not mocks
        tool_calls_to_save = None
        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            # Verify they're serializable (not mocks)
            try:
                json.dumps(tool_calls)
                tool_calls_to_save = tool_calls
            except (TypeError, ValueError):
                # If not serializable, don't save
                pass

        await self.db.add_message(
            conversation_id,
            "assistant",
            response_text,
            tool_calls=tool_calls_to_save,
        )

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "tool_calls": tool_calls,
        }

    async def chat_stream(
        self,
        conversation_id: Optional[str],
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate a streaming response to user message.

        This method streams the agent's response as it's being generated,
        enabling low-latency TTS that can start speaking before the complete
        response is ready.

        Args:
            conversation_id: Conversation ID, or None to create new
            user_message: User's message text

        Yields:
            Dict with 'type' field indicating event type:
                - {'type': 'conversation_id', 'conversation_id': str} - First event
                - {'type': 'text', 'content': str} - Text chunk from LLM
                - {'type': 'tool_call', 'name': str, 'input': dict, 'id': str} - Tool invocation
                - {'type': 'tool_result', 'content': str} - Tool execution result
                - {'type': 'done', 'full_text': str, 'tool_calls': list} - Stream complete
        """
        # Create new conversation if needed
        if conversation_id is None:
            conversation_id = await self.db.create_conversation(
                "New Conversation"  # Will be updated with generated title later
            )

        # Yield conversation_id as first event
        yield {"type": "conversation_id", "conversation_id": conversation_id}

        # Load conversation history
        history = await self.load_conversation_history(conversation_id)

        # Save user message to database
        await self.db.add_message(conversation_id, "user", user_message)

        logger.info(
            f"Processing streaming chat request for conversation {conversation_id}: '{user_message[:50]}...'"
        )

        # Prepare messages for agent
        messages_with_new = history + [
            {
                "role": "user",
                "content": [{"text": user_message}],
            }
        ]

        # Accumulate full response for database
        full_text = []
        tool_calls = []

        try:
            # Stream response from Strands agent
            async for event in self._strands_agent.stream_async(messages_with_new):
                # Events from Strands are dicts with different structures:
                # - {'data': '...', 'delta': {'text': '...'}} for streaming text chunks
                # - {'message': {...}} for complete messages
                # - {'event': {...}} for low-level events

                if isinstance(event, dict):
                    # Handle streaming text deltas (real-time text chunks)
                    if "data" in event and "delta" in event:
                        delta = event.get("delta", {})
                        if "text" in delta:
                            text_content = delta["text"]
                            if text_content:
                                full_text.append(text_content)
                                yield {"type": "text", "content": text_content}

                    # Handle complete message (contains tool calls if any)
                    elif "message" in event:
                        message = event["message"]
                        if isinstance(message, dict) and "content" in message:
                            for block in message["content"]:
                                # Tool use block
                                if "toolUse" in block:
                                    tool_use = block["toolUse"]
                                    tool_call_info = {
                                        "id": tool_use["toolUseId"],
                                        "name": tool_use["name"],
                                        "input": tool_use["input"],
                                    }
                                    tool_calls.append(tool_call_info)
                                    yield {
                                        "type": "tool_call",
                                        "name": tool_use["name"],
                                        "input": tool_use["input"],
                                        "id": tool_use["toolUseId"],
                                    }
                                    logger.info(f"Tool call: {tool_use['name']}")

                                # Tool result block
                                elif "toolResult" in block:
                                    tool_result = block["toolResult"]
                                    result_content = ""
                                    if "content" in tool_result:
                                        for result_block in tool_result["content"]:
                                            if "text" in result_block:
                                                result_content += result_block["text"]
                                    if result_content:
                                        yield {
                                            "type": "tool_result",
                                            "content": result_content,
                                            "tool_use_id": tool_result.get("toolUseId"),
                                        }

        except Exception as e:
            logger.error(f"Error during streaming agent invocation: {e}", exc_info=True)

            # Provide specific error messages based on error type
            error_str = str(e)
            if "No models loaded" in error_str:
                error_text = "No LLM model is currently loaded. Please load a model in LM Studio or your configured endpoint."
            elif "Connection refused" in error_str or "Failed to connect" in error_str:
                error_text = "Cannot connect to the LLM endpoint. Please ensure your LLM server is running."
            else:
                error_text = "I apologize, but I encountered an error processing your message. Please try again."

            full_text = [error_text]
            yield {"type": "text", "content": error_text}

        # Combine all text chunks
        response_text = "".join(full_text)

        logger.info(f"Streaming complete. Full response: '{response_text[:50]}...'")

        # Save agent response to database
        tool_calls_to_save = None
        if tool_calls:
            try:
                json.dumps(tool_calls)
                tool_calls_to_save = tool_calls
            except (TypeError, ValueError):
                pass

        await self.db.add_message(
            conversation_id,
            "assistant",
            response_text,
            tool_calls=tool_calls_to_save,
        )

        # Final event indicating stream is complete
        yield {
            "type": "done",
            "full_text": response_text,
            "tool_calls": tool_calls,
        }
