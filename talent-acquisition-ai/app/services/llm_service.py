"""
Qwen LLM service for text generation and embeddings.
Integrates with Alibaba Cloud DashScope API.
"""
import json
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


class QwenLLMService:
    """Service for interacting with Qwen LLM API."""

    def __init__(self):
        self.api_key = settings.qwen_api_key
        self.model = settings.qwen_model
        self.temperature = settings.qwen_temperature
        self.max_tokens = settings.qwen_max_tokens
        self.timeout = settings.qwen_timeout
        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        self.embedding_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using Qwen LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated text response
        """
        headers = self._get_headers()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "input": {
                "messages": messages,
            },
            "parameters": {
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
                "result_format": "message",
                **kwargs,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()

                result = response.json()

                if result.get("output"):
                    return result["output"]["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Unexpected API response format: {result}")
                    raise ValueError("Unexpected API response format")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during LLM generation: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing LLM response: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate structured JSON output using Qwen LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            schema: JSON schema for structured output
            **kwargs: Additional parameters

        Returns:
            Structured data as dictionary
        """
        if schema:
            prompt += f"\n\nPlease respond with valid JSON following this schema:\n{json.dumps(schema, indent=2)}"

        response_text = await self.generate(prompt, system_prompt, **kwargs)

        try:
            # Try to extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Response text: {response_text}")
            raise ValueError(f"Invalid JSON response: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text using Qwen embedding model.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        headers = self._get_headers()

        payload = {
            "model": settings.rag_embedding_model,
            "input": {
                "texts": [text],
            },
            "parameters": {
                "text_type": "document",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.embedding_url, headers=headers, json=payload)
                response.raise_for_status()

                result = response.json()

                if result.get("output") and result["output"].get("embeddings"):
                    return result["output"]["embeddings"][0]["embedding"]
                else:
                    logger.error(f"Unexpected embedding response format: {result}")
                    raise ValueError("Unexpected embedding response format")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during embedding generation: {e}")
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed(text)
            embeddings.append(embedding)
        return embeddings

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Chat with multiple message history.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream responses
            **kwargs: Additional parameters

        Returns:
            Generated response text
        """
        headers = self._get_headers()

        payload = {
            "model": self.model,
            "input": {
                "messages": messages,
            },
            "parameters": {
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
                "result_format": "message",
                "incremental_output": stream,
                **kwargs,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()

                result = response.json()

                if result.get("output"):
                    return result["output"]["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Unexpected API response format: {result}")
                    raise ValueError("Unexpected API response format")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during chat: {e}")
            raise


# Global LLM service instance
llm_service = QwenLLMService()
