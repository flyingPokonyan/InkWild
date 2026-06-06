"""Content publish/withdraw state machine for worlds and scripts.

States (active model — see docs/superpowers/specs/2026-05-30-publish-lifecycle-design.md):
  private     — owner-only, playable; the default landing state for a saved
                creation. Not listed in the public discover feed.
  submitted   — a revision is under admin review (P2). The review state lives
                on the *draft*, not on the World/Script row, so a published
                work can stay live while its revision is reviewed. This enum
                value is reserved for the draft.review_status field.
  published   — visible to all users.
  withdrawn   — admin force-removed; owner cannot self-recover.

Legacy:
  draft       — pre-lifecycle value. No World/Script rows use it in practice;
                kept so any straggler row can transition out cleanly.
"""
from enum import StrEnum


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PRIVATE = "private"
    SUBMITTED = "submitted"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


_VALID_TRANSITIONS = {
    # private library ↔ public
    (ContentStatus.PRIVATE, ContentStatus.PUBLISHED),
    (ContentStatus.PUBLISHED, ContentStatus.PRIVATE),  # owner unpublish / withdraw
    # review gate (P2) — submitted only ever lives on the draft, but the World
    # row may still flip private→published once approved.
    (ContentStatus.PRIVATE, ContentStatus.SUBMITTED),
    (ContentStatus.SUBMITTED, ContentStatus.PRIVATE),
    (ContentStatus.SUBMITTED, ContentStatus.PUBLISHED),
    # admin removal — owner cannot self-recover, but an admin can restore.
    (ContentStatus.PUBLISHED, ContentStatus.WITHDRAWN),
    # admin restore (un-withdraw) — only an admin can lift a takedown.
    (ContentStatus.WITHDRAWN, ContentStatus.PUBLISHED),
    # legacy stragglers
    (ContentStatus.DRAFT, ContentStatus.PRIVATE),
    (ContentStatus.DRAFT, ContentStatus.PUBLISHED),
}


def can_transition(src: ContentStatus, dst: ContentStatus) -> bool:
    return (src, dst) in _VALID_TRANSITIONS


def next_status_on_publish(*, audit_enabled: bool) -> ContentStatus:
    return ContentStatus.SUBMITTED if audit_enabled else ContentStatus.PUBLISHED


def next_status_on_withdraw(*, by_admin: bool) -> ContentStatus:
    """Owner withdraw returns to the private library; admin removal is terminal."""
    return ContentStatus.WITHDRAWN if by_admin else ContentStatus.PRIVATE
