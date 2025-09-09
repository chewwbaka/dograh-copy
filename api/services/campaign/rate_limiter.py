import time
import uuid
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL


class RateLimiter:
    """Sliding window rate limiter to enforce strict per-second limits and concurrent call limits"""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.stale_call_timeout = 1800  # 30 minutes in seconds

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection"""
        if self.redis_client is None:
            self.redis_client = await aioredis.from_url(
                REDIS_URL, decode_responses=True
            )
        return self.redis_client

    async def acquire_token(self, organization_id: int, rate_limit: int = 1) -> bool:
        """
        Enforces strict rate limit: max N calls per rolling second window
        Returns True if allowed, False if rate limited
        """
        redis_client = await self._get_redis()

        key = f"rate_limit:{organization_id}"
        now = time.time()
        window_start = now - 1.0  # 1 second sliding window

        # Lua script for atomic sliding window operation
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local max_requests = tonumber(ARGV[3])
        
        -- Remove timestamps older than window
        redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
        
        -- Count requests in current window
        local current_requests = redis.call('ZCARD', key)
        
        if current_requests < max_requests then
            -- Add current timestamp
            redis.call('ZADD', key, now, now)
            redis.call('EXPIRE', key, 2)  -- Expire after 2 seconds
            return 1
        else
            return 0
        end
        """

        try:
            result = await redis_client.eval(
                lua_script, 1, key, now, window_start, rate_limit
            )
            return bool(result)
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            # On error, be conservative and deny
            return False

    async def get_next_available_slot(
        self, organization_id: int, rate_limit: int = 1
    ) -> float:
        """
        Returns seconds until next available slot
        Useful for implementing retry with backoff
        """
        redis_client = await self._get_redis()

        key = f"rate_limit:{organization_id}"

        try:
            # Get oldest timestamp in current window
            oldest = await redis_client.zrange(key, 0, 0, withscores=True)
            if not oldest:
                return 0.0  # Can call immediately

            oldest_time = oldest[0][1]
            next_available = oldest_time + 1.0  # 1 second after oldest
            wait_time = max(0, next_available - time.time())

            return wait_time
        except Exception as e:
            logger.error(f"Rate limiter get_next_available_slot error: {e}")
            return 1.0  # Default wait time on error

    async def try_acquire_concurrent_slot(
        self, organization_id: int, max_concurrent: int = 20
    ) -> Optional[str]:
        """
        Try to acquire a concurrent call slot.
        Returns a unique slot_id if successful, None if limit reached.
        """
        redis_client = await self._get_redis()

        concurrent_key = f"concurrent_calls:{organization_id}"
        now = time.time()
        stale_cutoff = now - self.stale_call_timeout

        # Lua script for atomic operation
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local max_concurrent = tonumber(ARGV[2])
        local stale_cutoff = tonumber(ARGV[3])
        local slot_id = ARGV[4]
        
        -- Remove stale entries (older than 30 minutes)
        redis.call('ZREMRANGEBYSCORE', key, 0, stale_cutoff)
        
        -- Get current count
        local current_count = redis.call('ZCARD', key)
        
        if current_count < max_concurrent then
            -- Add new slot
            redis.call('ZADD', key, now, slot_id)
            redis.call('EXPIRE', key, 3600)  -- Expire after 1 hour
            return slot_id
        else
            return nil
        end
        """

        # Generate unique slot ID (timestamp + random component)
        slot_id = f"{int(now * 1000)}_{uuid.uuid4().hex[:8]}"

        try:
            result = await redis_client.eval(
                lua_script,
                1,
                concurrent_key,
                now,
                max_concurrent,
                stale_cutoff,
                slot_id,
            )
            return result
        except Exception as e:
            logger.error(f"Concurrent limiter error: {e}")
            return None

    async def release_concurrent_slot(self, organization_id: int, slot_id: str) -> bool:
        """
        Release a concurrent call slot.
        Returns True if slot was released, False otherwise.
        """
        if not slot_id:
            return False

        redis_client = await self._get_redis()
        concurrent_key = f"concurrent_calls:{organization_id}"

        try:
            removed = await redis_client.zrem(concurrent_key, slot_id)
            if removed:
                logger.debug(
                    f"Released concurrent slot {slot_id} for org {organization_id}"
                )
            return bool(removed)
        except Exception as e:
            logger.error(f"Error releasing concurrent slot: {e}")
            return False

    async def get_concurrent_count(self, organization_id: int) -> int:
        """
        Get current number of active concurrent calls for an organization.
        Automatically cleans up stale entries.
        """
        redis_client = await self._get_redis()
        concurrent_key = f"concurrent_calls:{organization_id}"

        try:
            # Clean up stale entries first
            stale_cutoff = time.time() - self.stale_call_timeout
            await redis_client.zremrangebyscore(concurrent_key, 0, stale_cutoff)

            # Get current count
            count = await redis_client.zcard(concurrent_key)
            return count
        except Exception as e:
            logger.error(f"Error getting concurrent count: {e}")
            return 0

    async def store_workflow_slot_mapping(
        self, workflow_run_id: int, organization_id: int, slot_id: str
    ) -> bool:
        """
        Store the mapping between workflow_run_id and its concurrent slot.
        Used for cleanup when calls complete.
        """
        redis_client = await self._get_redis()
        mapping_key = f"workflow_slot_mapping:{workflow_run_id}"

        try:
            # Store as a hash with TTL
            await redis_client.hset(
                mapping_key, mapping={"org_id": organization_id, "slot_id": slot_id}
            )
            # Set expiry to match stale timeout
            await redis_client.expire(mapping_key, self.stale_call_timeout)
            return True
        except Exception as e:
            logger.error(f"Error storing workflow slot mapping: {e}")
            return False

    async def get_workflow_slot_mapping(
        self, workflow_run_id: int
    ) -> Optional[tuple[int, str]]:
        """
        Get the concurrent slot mapping for a workflow run.
        Returns (organization_id, slot_id) tuple or None if not found.
        """
        redis_client = await self._get_redis()
        mapping_key = f"workflow_slot_mapping:{workflow_run_id}"

        try:
            mapping = await redis_client.hgetall(mapping_key)
            if mapping and "org_id" in mapping and "slot_id" in mapping:
                return (int(mapping["org_id"]), mapping["slot_id"])
            return None
        except Exception as e:
            logger.error(f"Error getting workflow slot mapping: {e}")
            return None

    async def delete_workflow_slot_mapping(self, workflow_run_id: int) -> bool:
        """
        Delete the workflow slot mapping after releasing the slot.
        """
        redis_client = await self._get_redis()
        mapping_key = f"workflow_slot_mapping:{workflow_run_id}"

        try:
            deleted = await redis_client.delete(mapping_key)
            return bool(deleted)
        except Exception as e:
            logger.error(f"Error deleting workflow slot mapping: {e}")
            return False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None


# Global rate limiter instance
rate_limiter = RateLimiter()
