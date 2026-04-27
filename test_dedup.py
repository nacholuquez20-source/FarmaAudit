"""Test suite for loop prevention mechanisms."""

import pytest
import asyncio

from main import (
    _is_message_processed,
    _mark_message_processed,
    _claim_message_for_processing,
    _release_message_claim,
    _processed_messages,
    _processing_messages,
    _get_supabase_client,
)
from router import ConversationRouter


@pytest.fixture(autouse=True)
def cleanup_supabase_dedup():
    """Clean webhook_dedup table before each test."""
    client = _get_supabase_client()
    if client is not None:
        try:
            client.table("webhook_dedup").delete().neq("message_id", "").execute()
        except Exception:
            pass
    yield


@pytest.mark.asyncio
async def test_message_deduplication():
    """Test message deduplication by message_id."""
    # Clear cache
    _processed_messages.clear()
    _processing_messages.clear()

    message_id = "test_msg_123"
    phone = "5491234567890"

    # First call: should not be processed
    assert not _is_message_processed(message_id)

    # Mark as processed
    await _mark_message_processed(message_id, phone)

    # Second call: should be marked as processed
    assert _is_message_processed(message_id)

    # Verify cache entry
    assert message_id in _processed_messages
    assert _processed_messages[message_id][1] == phone


@pytest.mark.asyncio
async def test_concurrent_messages_same_auditor():
    """Test that concurrent messages for same auditor are serialized."""
    # Test locks without initializing ConversationRouter (avoids credential loading)
    phone = "5491234567890"
    lock1 = await ConversationRouter._get_conversation_lock(phone)
    lock2 = await ConversationRouter._get_conversation_lock(phone)

    # Locks for same phone should be identical
    assert lock1 is lock2


@pytest.mark.asyncio
async def test_concurrent_messages_different_auditors():
    """Test that messages for different auditors use different locks."""
    # Test locks without initializing ConversationRouter
    phone1 = "5491234567890"
    phone2 = "5491234567891"
    lock1 = await ConversationRouter._get_conversation_lock(phone1)
    lock2 = await ConversationRouter._get_conversation_lock(phone2)

    # Locks for different phones should be different
    assert lock1 is not lock2


@pytest.mark.asyncio
async def test_concurrent_processing_blocked():
    """Test that concurrent processing of same conversation is blocked."""
    phone = "5491234567890"

    processing_order = []

    async def mock_handle(delay_ms, name):
        lock = await ConversationRouter._get_conversation_lock(phone)
        async with lock:
            processing_order.append(f"{name}_start")
            await asyncio.sleep(delay_ms / 1000)
            processing_order.append(f"{name}_end")

    # Start two concurrent tasks for same phone
    task1 = asyncio.create_task(mock_handle(10, "A"))
    task2 = asyncio.create_task(mock_handle(5, "B"))

    await asyncio.gather(task1, task2)

    # Verify serialization: A starts, A ends, then B starts, B ends
    assert processing_order == ["A_start", "A_end", "B_start", "B_end"] or \
           processing_order == ["B_start", "B_end", "A_start", "A_end"]


@pytest.mark.asyncio
async def test_message_dedup_ttl_expiry():
    """Test that message_id entries expire after TTL."""
    from main import _MESSAGE_TTL_SECONDS

    _processed_messages.clear()
    _processing_messages.clear()

    message_id = "test_expiry"
    phone = "5491234567890"

    await _mark_message_processed(message_id, phone)
    assert _is_message_processed(message_id)

    # Manually expire the entry
    old_timestamp, _ = _processed_messages[message_id]
    from datetime import timedelta
    _processed_messages[message_id] = (
        old_timestamp - timedelta(seconds=_MESSAGE_TTL_SECONDS + 1),
        phone
    )

    # Should be expired now
    assert not _is_message_processed(message_id)


@pytest.mark.asyncio
async def test_atomic_claim_prevents_concurrent_duplicate_processing():
    """Only one concurrent request can claim same message_id."""
    _processed_messages.clear()
    _processing_messages.clear()

    message_id = "msg_atomic_1"
    phone = "5491234567890"

    async def attempt_claim():
        return await _claim_message_for_processing(message_id, phone)

    claimed_a, claimed_b = await asyncio.gather(attempt_claim(), attempt_claim())
    assert sum([claimed_a, claimed_b]) == 1

    # Mark success and verify future attempts are rejected
    await _mark_message_processed(message_id, phone)
    assert not await _claim_message_for_processing(message_id, phone)


@pytest.mark.asyncio
async def test_claim_released_after_failure():
    """Claim can be released so retries are possible after failures."""
    _processed_messages.clear()
    _processing_messages.clear()

    message_id = "msg_atomic_2"
    phone = "5491234567890"

    assert await _claim_message_for_processing(message_id, phone)
    assert not await _claim_message_for_processing(message_id, phone)

    await _release_message_claim(message_id)
    assert await _claim_message_for_processing(message_id, phone)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
