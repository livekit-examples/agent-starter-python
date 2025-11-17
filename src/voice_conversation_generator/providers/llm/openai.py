"""
OpenAI LLM Provider Implementation
"""
import os
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from ..base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    """OpenAI LLM provider for GPT models"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI client

        Config should include:
        - api_key: OpenAI API key (or from env OPENAI_API_KEY)
        - model: Model name (e.g., 'gpt-4', 'gpt-3.5-turbo')
        - organization: Optional organization ID
        """
        super().__init__(config)

        # Get API key from config or environment
        api_key = config.get('api_key') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found in config or environment")

        # Initialize client
        self.client = AsyncOpenAI(
            api_key=api_key,
            organization=config.get('organization')
        )

        # Set default model
        self.model = config.get('model', 'gpt-4')

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 150,
        **kwargs
    ) -> str:
        """Generate text completion from OpenAI

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Temperature for sampling (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.generate_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 150,
        **kwargs
    ) -> str:
        """Generate chat completion from OpenAI

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Temperature for sampling (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Returns:
            Generated text response
        """
        # Handle model-specific parameters
        model = kwargs.pop('model', self.model)

        # Adjust parameters for newer models
        completion_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        # Use max_completion_tokens for newer models (gpt-5, gpt-4.1, gpt-4o series)
        if model.startswith('gpt-5') or model.startswith('gpt-4.') or model in ['gpt-4o', 'gpt-4o-mini']:
            completion_params["max_completion_tokens"] = max_tokens
        else:
            completion_params["max_tokens"] = max_tokens

        # Add any additional parameters
        completion_params.update(kwargs)

        try:
            response = await self.client.chat.completions.create(**completion_params)
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"OpenAI completion failed: {e}")

    def get_model_name(self) -> str:
        """Get the name of the model being used"""
        return self.model