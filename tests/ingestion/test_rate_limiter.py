"""
Tests for the RateLimiter and RateLimitWindow classes.
Covers sliding window algorithm, group suspension, and burst handling.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from graphiti_core.ingestion.worker import (
    RateLimiter,
    RateLimitWindow,
    RateLimitError,
)


class TestRateLimitWindow:
    """Tests for the RateLimitWindow sliding window implementation."""

    def test_empty_window_allows_request(self):
        """Empty window should allow requests."""
        window = RateLimitWindow(requests=[], limit=10, window_seconds=60)
        assert window.is_allowed() is True

    def test_under_limit_allows_request(self):
        """Should allow requests when under the limit."""
        now = time.time()
        window = RateLimitWindow(requests=[now - 10, now - 5, now - 1], limit=10, window_seconds=60)
        assert window.is_allowed() is True

    def test_at_limit_denies_request(self):
        """Should deny requests when at the limit."""
        now = time.time()
        window = RateLimitWindow(requests=[now - i for i in range(10)], limit=10, window_seconds=60)
        assert window.is_allowed() is False

    def test_old_requests_are_cleaned_up(self):
        """Should remove requests older than window_seconds."""
        now = time.time()
        old_requests = [now - 120, now - 90, now - 70]  # All older than 60s
        recent_requests = [now - 30, now - 10]  # Within window

        window = RateLimitWindow(
            requests=old_requests + recent_requests, limit=10, window_seconds=60
        )

        # Calling is_allowed should clean up old requests
        assert window.is_allowed() is True
        assert len(window.requests) == 2  # Only recent requests remain

    def test_record_request_adds_timestamp(self):
        """Should record current timestamp when recording a request."""
        window = RateLimitWindow(requests=[], limit=10, window_seconds=60)

        before = time.time()
        window.record_request()
        after = time.time()

        assert len(window.requests) == 1
        assert before <= window.requests[0] <= after

    def test_window_respects_custom_window_seconds(self):
        """Should use the configured window_seconds for cleanup."""
        now = time.time()
        # Requests at 5 seconds ago (within 10s window, outside 3s window)
        window_short = RateLimitWindow(requests=[now - 5], limit=1, window_seconds=3)
        window_long = RateLimitWindow(requests=[now - 5], limit=1, window_seconds=10)

        # Short window should have cleaned up the request
        assert window_short.is_allowed() is True
        # Long window should still have the request
        assert window_long.is_allowed() is False


class TestRateLimiter:
    """Tests for the RateLimiter with global and per-group limits."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh rate limiter for each test."""
        return RateLimiter(global_rps=100, group_rpm=60, burst_multiplier=1.5)

    @pytest.mark.asyncio
    async def test_allows_request_under_limits(self, limiter):
        """Should allow requests when under all limits."""
        result = await limiter.acquire(group_id='test-group')
        assert result is True

    @pytest.mark.asyncio
    async def test_global_limit_exceeded(self, limiter):
        """Should raise RateLimitError when global limit exceeded."""
        # Fill up global window
        limiter.global_window.requests = [time.time()] * 100

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(group_id='test-group')

        assert exc_info.value.group_id == 'global'
        assert exc_info.value.retry_after == 1

    @pytest.mark.asyncio
    async def test_group_limit_exceeded(self, limiter):
        """Should raise RateLimitError and suspend group when limit exceeded."""
        # Fill up group window
        limiter.group_windows['test-group'] = RateLimitWindow(
            requests=[time.time()] * 60, limit=60, window_seconds=60
        )

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(group_id='test-group')

        assert exc_info.value.group_id == 'test-group'
        assert exc_info.value.retry_after == 60
        assert 'test-group' in limiter.suspended_groups

    @pytest.mark.asyncio
    async def test_suspended_group_raises_error(self, limiter):
        """Should raise RateLimitError for suspended groups."""
        # Manually suspend group
        limiter.suspend_group('suspended-group', duration_seconds=300)

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(group_id='suspended-group')

        assert exc_info.value.group_id == 'suspended-group'

    def test_is_group_suspended_returns_false_for_unknown(self, limiter):
        """Should return False for groups that were never suspended."""
        assert limiter.is_group_suspended('unknown-group') is False

    def test_is_group_suspended_returns_true_during_suspension(self, limiter):
        """Should return True for groups within suspension window."""
        limiter.suspend_group('test-group', duration_seconds=300)
        assert limiter.is_group_suspended('test-group') is True

    def test_suspension_expires_after_duration(self, limiter):
        """Should return False after suspension duration expires."""
        # Suspend for 0 seconds (immediate expiry)
        limiter.suspended_groups['test-group'] = datetime.utcnow() - timedelta(seconds=1)

        assert limiter.is_group_suspended('test-group') is False
        assert 'test-group' not in limiter.suspended_groups

    def test_suspend_group_sets_expiry_time(self, limiter):
        """Should set correct expiry time when suspending."""
        before = datetime.utcnow()
        limiter.suspend_group('test-group', duration_seconds=60)
        after = datetime.utcnow()

        expected_min = before + timedelta(seconds=60)
        expected_max = after + timedelta(seconds=60)

        assert expected_min <= limiter.suspended_groups['test-group'] <= expected_max

    @pytest.mark.asyncio
    async def test_creates_group_window_on_first_request(self, limiter):
        """Should create a group window on first request for that group."""
        assert 'new-group' not in limiter.group_windows

        await limiter.acquire(group_id='new-group')

        assert 'new-group' in limiter.group_windows
        assert isinstance(limiter.group_windows['new-group'], RateLimitWindow)

    @pytest.mark.asyncio
    async def test_records_request_in_both_windows(self, limiter):
        """Should record request in both global and group windows."""
        initial_global = len(limiter.global_window.requests)

        await limiter.acquire(group_id='test-group')

        assert len(limiter.global_window.requests) == initial_global + 1
        assert len(limiter.group_windows['test-group'].requests) == 1

    @pytest.mark.asyncio
    async def test_no_group_id_only_checks_global(self, limiter):
        """Should only check global limit when no group_id provided."""
        result = await limiter.acquire(group_id=None)
        assert result is True

        # Should not create any group windows
        assert len(limiter.group_windows) == 0

    @pytest.mark.asyncio
    async def test_multiple_groups_tracked_independently(self, limiter):
        """Should track rate limits independently for different groups."""
        # Exhaust group-a's limit
        limiter.group_windows['group-a'] = RateLimitWindow(
            requests=[time.time()] * 60, limit=60, window_seconds=60
        )

        # group-a should be rate limited
        with pytest.raises(RateLimitError):
            await limiter.acquire(group_id='group-a')

        # group-b should still work
        result = await limiter.acquire(group_id='group-b')
        assert result is True

    @pytest.mark.asyncio
    async def test_burst_multiplier_stored(self, limiter):
        """Should store burst_multiplier for potential future use."""
        custom_limiter = RateLimiter(global_rps=100, group_rpm=60, burst_multiplier=2.0)
        assert custom_limiter.burst_multiplier == 2.0


class TestRateLimitError:
    """Tests for the RateLimitError exception."""

    def test_error_contains_group_id(self):
        """Should store group_id in the exception."""
        error = RateLimitError(group_id='test-group', retry_after=60)
        assert error.group_id == 'test-group'

    def test_error_contains_retry_after(self):
        """Should store retry_after in the exception."""
        error = RateLimitError(group_id='test-group', retry_after=120)
        assert error.retry_after == 120

    def test_error_default_retry_after(self):
        """Should use default retry_after of 60 seconds."""
        error = RateLimitError(group_id='test-group')
        assert error.retry_after == 60

    def test_error_message_format(self):
        """Should have descriptive error message."""
        error = RateLimitError(group_id='test-group', retry_after=60)
        assert 'test-group' in str(error)
        assert 'Rate limit' in str(error)
