import shelve
import hashlib

import logging
logger = logging.getLogger(__name__)

from app.llm_usage import LLMUsage

class LLMCache:
    def __init__(self, filename: str):
        self.filename = filename

    def _hash_key(self, key: str) -> str:
        # Converts the key into a unique SHA-256 string
        return hashlib.sha256(str(key).encode('utf-8')).hexdigest()

    def set(self, key: str, output: str, usage: LLMUsage | None = None):
        logger.debug(f"caching key {key} with value {output}")
        hashed_key = self._hash_key(key)
        with shelve.open(self.filename) as f:
            f[hashed_key] = (output, usage)

    def get(self, key: str, default=None) -> tuple[str, LLMUsage] | None:
        hashed_key = self._hash_key(key)
        with shelve.open(self.filename) as f:
            result = f.get(hashed_key, default)
            if isinstance(result, tuple):
                return result
            elif isinstance(result, str):
                return result, LLMUsage()
            return None