"""
Model routing and cost calculation logic
"""
import re
from typing import Optional, Tuple
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import MODELS, ModelConfig

class ModelRouter:
    """
    Routes prompts to appropriate models based on complexity
    Uses simple heuristics to avoid dependency on tiktoken
    """
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough token estimation without external dependencies
        Rule of thumb: ~0.75 words per token for English
        """
        # Split on whitespace and punctuation
        words = re.findall(r'\b\w+\b', text)
        # Approximate: 1 token per 0.75 words, this seems to be the standard
        return max(1, int(len(words) / 0.75))
    
    @staticmethod
    def select_model(prompt: str, requested_model: Optional[str] = None) -> ModelConfig:
        """
        Select optimal model based on prompt complexity

        TODO: this is fake complexity. tokens dont necessarily reflect complexity. plus, we will probably hit 200 pretty easily with all the behind the scenes prompting.
        
        Strategy:
        - User preference always wins if valid
        - < 50 tokens (~35 words): Use cheap model for simple queries
        - 50-200 tokens (~35-150 words): Use balanced model
        - > 200 tokens (>150 words): Use premium for complex tasks
        """
        # Honor explicit model request
        if requested_model:
            for tier_config in MODELS.values():
                if tier_config.name == requested_model:
                    return tier_config
        
        # Route by estimated complexity
        estimated_tokens = ModelRouter.estimate_tokens(prompt)
        
        if estimated_tokens < 50:
            return MODELS["cheap"]
        elif estimated_tokens < 200:
            return MODELS["balanced"]
        else:
            return MODELS["premium"]
    
    @staticmethod
    def parse_usage(response: dict) -> Tuple[int, int]:
        """
        Extract token counts from OpenRouter response
        Returns (input_tokens, output_tokens)
        """
        usage = response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        return input_tokens, output_tokens