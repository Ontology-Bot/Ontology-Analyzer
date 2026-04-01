import shelve
import hashlib

import logging
logger = logging.getLogger(__name__)

class LLMCache:
    def __init__(self, filename: str):
        self.filename = filename

    def _hash_key(self, key: str) -> str:
        # Converts the key into a unique SHA-256 string
        return hashlib.sha256(str(key).encode('utf-8')).hexdigest()

    def set(self, key: str, val: str):
        logger.debug(f"caching key {key} with value {val}")
        hashed_key = self._hash_key(key)
        with shelve.open(self.filename) as f:
            f[hashed_key] = val

    def get(self, key: str, default=None):
        hashed_key = self._hash_key(key)
        with shelve.open(self.filename) as f:
            return f.get(hashed_key, default)