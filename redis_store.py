import json
import redis
from config import config


class RedisStore:
    def __init__(self):
        self.client = None

        if config.UPSTASH_REDIS_URL:
            self.client = redis.from_url(
                config.UPSTASH_REDIS_URL,
                decode_responses=True,
                ssl_cert_reqs=None,
            )

    def available(self) -> bool:
        return self.client is not None

    def set_json(self, key: str, value, ttl: int = 180):
        if not self.client:
            return
        self.client.setex(key, ttl, json.dumps(value, default=str))

    def get_json(self, key: str, default=None):
        if not self.client:
            return default

        raw = self.client.get(key)
        if raw is None:
            return default

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default


store = RedisStore()
