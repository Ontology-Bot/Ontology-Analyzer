from dataclasses import dataclass

@dataclass
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    duration: float | None = None

    def __bool__(self):
        return any(value is not None for value in [self.prompt_tokens, self.completion_tokens, self.total_tokens, self.duration])
    
    def model_dump(self):
        if not self:
            return None
        return {
            # "prompt_tokens": self.prompt_tokens,
            # "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration": self.duration
        }
