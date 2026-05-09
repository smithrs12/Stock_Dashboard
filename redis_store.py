import json
import redis
from config import config


class RedisStore:
    def __init__(self):
        self.client = None

        if config.UPSTASH_REDIS_URL:
            try:
                self.client = redis.from_url(
                    config.UPSTASH_REDIS_URL,
                    decode_responses=True,
                    ssl_cert_reqs=None,
                )
            except Exception as exc:
                print(f"[redis_store] failed to connect to Redis: {exc}")
                self.client = None

    def available(self) -> bool:
        return self.client is not None

    def set_json(self, key: str, value, ttl: int = 180):
        if not self.client:
            return

        try:
            self.client.setex(key, ttl, json.dumps(value, default=str))
        except Exception as exc:
            print(f"[redis_store] set_json failed for key={key}: {exc}")

    def get_json(self, key: str, default=None):
        if not self.client:
            return default

        try:
            raw = self.client.get(key)
            if raw is None:
                return default
            return json.loads(raw)
        except Exception as exc:
            print(f"[redis_store] get_json failed for key={key}: {exc}")
            return default

    def delete(self, key: str):
        if not self.client:
            return

        try:
            self.client.delete(key)
        except Exception as exc:
            print(f"[redis_store] delete failed for key={key}: {exc}")

    def set_value(self, key: str, value: str, ttl: int = 180):
        if not self.client:
            return

        try:
            self.client.setex(key, ttl, value)
        except Exception as exc:
            print(f"[redis_store] set_value failed for key={key}: {exc}")

    def get_value(self, key: str, default=None):
        if not self.client:
            return default

        try:
            value = self.client.get(key)
            return value if value is not None else default
        except Exception as exc:
            print(f"[redis_store] get_value failed for key={key}: {exc}")
            return default


store = RedisStore()
