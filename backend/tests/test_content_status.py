import pytest
from engine.content_status import (
    ContentStatus,
    can_transition,
    next_status_on_publish,
    next_status_on_withdraw,
)


def test_valid_transitions():
    # private library ↔ public
    assert can_transition(ContentStatus.PRIVATE, ContentStatus.PUBLISHED)
    assert can_transition(ContentStatus.PUBLISHED, ContentStatus.PRIVATE)
    # review gate
    assert can_transition(ContentStatus.PRIVATE, ContentStatus.SUBMITTED)
    assert can_transition(ContentStatus.SUBMITTED, ContentStatus.PUBLISHED)
    assert can_transition(ContentStatus.SUBMITTED, ContentStatus.PRIVATE)
    # admin removal + admin restore (un-withdraw → back online)
    assert can_transition(ContentStatus.PUBLISHED, ContentStatus.WITHDRAWN)
    assert can_transition(ContentStatus.WITHDRAWN, ContentStatus.PUBLISHED)


def test_invalid_transitions():
    # withdrawn → private is not allowed: owner cannot self-recover, and admin
    # restore goes straight back to published (handled by restore_*).
    assert not can_transition(ContentStatus.WITHDRAWN, ContentStatus.PRIVATE)
    # a private work cannot be force-withdrawn (nothing public to remove)
    assert not can_transition(ContentStatus.PRIVATE, ContentStatus.WITHDRAWN)
    # a live published work's revision is reviewed on the draft, not by
    # flipping the World row to submitted
    assert not can_transition(ContentStatus.PUBLISHED, ContentStatus.SUBMITTED)


def test_publish_path_respects_audit_flag():
    assert next_status_on_publish(audit_enabled=False) == ContentStatus.PUBLISHED
    assert next_status_on_publish(audit_enabled=True) == ContentStatus.SUBMITTED


def test_withdraw_actor():
    # owner unpublish returns to the private library; admin removal is terminal
    assert next_status_on_withdraw(by_admin=False) == ContentStatus.PRIVATE
    assert next_status_on_withdraw(by_admin=True) == ContentStatus.WITHDRAWN
