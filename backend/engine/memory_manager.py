from __future__ import annotations

import structlog
from sqlalchemy import select

from models.memory import MemoryEntry
from services.embedding_service import cosine_similarity, embed_text, embed_texts

IMPORTANCE_MAP = {"high": 8, "medium": 5, "low": 3}

# When semantic recall is active, pull a wider candidate pool (importance
# top-N) before re-ranking by cosine similarity. 3x the final limit gives
# the embedding pass enough room to surface relevant entries that wouldn't
# rank in the top-K by raw importance.
_SEMANTIC_CANDIDATE_MULTIPLIER = 3
_SEMANTIC_CANDIDATE_MIN = 20

logger = structlog.get_logger()


class MemoryManager:
    def parse_memory_extracts(
        self,
        tool_output: dict,
        session_id: str,
        round_number: int,
        known_npcs: list[str] | None = None,
    ) -> list[dict]:
        extracts = tool_output.get("memory_extracts", [])
        if not extracts:
            return []

        entries: list[dict] = []
        for extract in extracts:
            content = str(extract.get("content") or "").strip()
            if not content:
                continue
            related_npc = self._detect_npc(content, known_npcs or [])
            entries.append(
                {
                    "session_id": session_id,
                    "memory_type": str(extract.get("type") or "general"),
                    "content": content,
                    "round_number": round_number,
                    "importance": IMPORTANCE_MAP.get(str(extract.get("importance") or "medium"), 5),
                    "related_npc": related_npc,
                }
            )
        return entries

    def _detect_npc(self, content: str, known_npcs: list[str]) -> str | None:
        for npc_name in known_npcs:
            if npc_name in content:
                return npc_name
        return None

    def write_dual_perspective_memories(
        self,
        session_id: str,
        round_number: int,
        npc_a: str,
        npc_b: str,
        event_description: str,
        perspective_a: str,
        perspective_b: str,
    ) -> list[dict]:
        return [
            {
                "session_id": session_id,
                "memory_type": "npc_interaction",
                "content": perspective_a,
                "round_number": round_number,
                "importance": 7,
                "related_npc": npc_a,
            },
            {
                "session_id": session_id,
                "memory_type": "npc_interaction",
                "content": perspective_b,
                "round_number": round_number,
                "importance": 7,
                "related_npc": npc_b,
            },
        ]

    def write_info_propagation_memories(
        self,
        session_id: str,
        round_number: int,
        events: list,
    ) -> list[dict]:
        entries: list[dict] = []
        for event in events:
            if getattr(event, "event_type", "") != "info_spread":
                continue
            description = str(getattr(event, "description", "")).strip()
            if not description:
                continue
            for npc_name in getattr(event, "involved_npcs", []) or []:
                if not npc_name:
                    continue
                entries.append(
                    {
                        "session_id": session_id,
                        "memory_type": "info_propagation",
                        "content": description,
                        "round_number": round_number,
                        "importance": 5,
                        "related_npc": str(npc_name),
                    }
                )
        return entries

    def filter_npc_memory_entries(self, entries: list[dict], npc_name: str) -> list[dict]:
        return [
            entry
            for entry in entries
            if str(entry.get("related_npc") or "") == npc_name
        ]

    async def query_npc_memories(
        self,
        db,
        session_id: str,
        npc_name: str,
        limit: int = 10,
        query_text: str | None = None,
    ) -> list[dict]:
        """Recall NPC-scoped memories.

        When ``query_text`` is provided AND the embedding service is
        configured, pulls a wider importance-ordered candidate pool then
        re-ranks by cosine similarity to ``query_text``. Falls back to plain
        importance/round ordering when embeddings are unavailable or every
        candidate row has a NULL embedding.
        """
        candidate_limit = (
            max(limit * _SEMANTIC_CANDIDATE_MULTIPLIER, _SEMANTIC_CANDIDATE_MIN)
            if query_text
            else limit
        )
        stmt = (
            select(MemoryEntry)
            .where(MemoryEntry.session_id == session_id, MemoryEntry.related_npc == npc_name)
            .order_by(MemoryEntry.importance.desc(), MemoryEntry.round_number.desc())
            .limit(candidate_limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return []

        if query_text:
            reranked = await self._semantic_rerank(rows, query_text, limit)
            if reranked is not None:
                return reranked

        return [
            {
                "memory_type": row.memory_type,
                "content": row.content,
                "round_number": row.round_number,
                "importance": row.importance,
            }
            for row in rows[:limit]
        ]

    async def _semantic_rerank(
        self,
        rows: list[MemoryEntry],
        query_text: str,
        limit: int,
    ) -> list[dict] | None:
        """Re-rank candidate rows by cosine similarity to query_text.

        Returns None if recall must fall back to the legacy ordering
        (no embedding service, or none of the candidate rows has an embedding).
        Rows without an embedding are kept but ranked by importance only,
        appearing after embedding-ranked rows.
        """
        rows_with_embedding = [row for row in rows if row.embedding]
        if not rows_with_embedding:
            return None

        query_vec = await embed_text(query_text)
        if not query_vec:
            return None

        scored: list[tuple[float, MemoryEntry]] = []
        for row in rows:
            if row.embedding:
                score = cosine_similarity(query_vec, row.embedding)
            else:
                # Sentinel below any plausible cosine value so embedded rows
                # always win when available.
                score = -1.0
            scored.append((score, row))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "memory_type": row.memory_type,
                "content": row.content,
                "round_number": row.round_number,
                "importance": row.importance,
                "similarity": score if score >= 0 else None,
            }
            for score, row in scored[:limit]
        ]

    async def batch_query_npc_memories(
        self,
        db,
        session_id: str,
        npc_names: list[str],
        limit_per_npc: int = 10,
        query_text: str | None = None,
    ) -> dict[str, list[dict]]:
        """Phase 2.D.3 — single-SQL batch version of query_npc_memories.

        Pulls memory rows for ALL ``npc_names`` in one query, groups them per
        NPC in Python, then (when ``query_text`` is set) embeds query_text
        once and re-ranks each NPC's candidate set by cosine. Eliminates the
        N+1 problem from per-NPC queries.

        Returns ``{npc_name: [memory_dict, ...]}``. NPCs with no memories
        get an empty list in the dict.
        """
        if not npc_names:
            return {}

        candidate_limit_per_npc = (
            max(limit_per_npc * _SEMANTIC_CANDIDATE_MULTIPLIER, _SEMANTIC_CANDIDATE_MIN)
            if query_text
            else limit_per_npc
        )

        stmt = (
            select(MemoryEntry)
            .where(
                MemoryEntry.session_id == session_id,
                MemoryEntry.related_npc.in_(npc_names),
            )
            .order_by(
                MemoryEntry.importance.desc(),
                MemoryEntry.round_number.desc(),
            )
        )
        result = await db.execute(stmt)
        all_rows = result.scalars().all()

        by_npc: dict[str, list[MemoryEntry]] = {n: [] for n in npc_names}
        for row in all_rows:
            bucket = by_npc.get(row.related_npc)
            if bucket is None:
                continue
            if len(bucket) >= candidate_limit_per_npc:
                continue
            bucket.append(row)

        # Embed query once, reuse for every NPC's rerank pass.
        query_vec: list[float] | None = None
        if query_text:
            try:
                query_vec = await embed_text(query_text)
            except Exception:  # noqa: BLE001
                logger.warning("batch_query_embed_failed", exc_info=True)
                query_vec = None

        output: dict[str, list[dict]] = {}
        for npc_name in npc_names:
            rows = by_npc.get(npc_name, [])
            if not rows:
                output[npc_name] = []
                continue

            should_rerank = query_vec is not None and any(r.embedding for r in rows)
            if should_rerank:
                scored: list[tuple[float, MemoryEntry]] = []
                for r in rows:
                    if r.embedding:
                        score = cosine_similarity(query_vec, r.embedding)
                    else:
                        score = -1.0
                    scored.append((score, r))
                scored.sort(key=lambda pair: pair[0], reverse=True)
                output[npc_name] = [
                    {
                        "memory_type": r.memory_type,
                        "content": r.content,
                        "round_number": r.round_number,
                        "importance": r.importance,
                        "similarity": s if s >= 0 else None,
                    }
                    for s, r in scored[:limit_per_npc]
                ]
            else:
                output[npc_name] = [
                    {
                        "memory_type": r.memory_type,
                        "content": r.content,
                        "round_number": r.round_number,
                        "importance": r.importance,
                    }
                    for r in rows[:limit_per_npc]
                ]

        return output

    async def get_npc_peer_relations(
        self,
        db,
        session_id: str,
        npc_name: str,
    ) -> list[dict]:
        """NPC-2 — return the asking NPC's outgoing relations only.

        Information isolation (npc.md §4): the caller sees how *they* view
        each peer; the reverse direction (B→A trust) is never returned, and
        unrelated C↔D relations are never returned. This matches the "no
        telepathy" rule — an NPC shouldn't know how others feel about them
        unless that's been explicitly written into their own memory.
        """
        from models.npc_relation import NPCRelation

        stmt = (
            select(NPCRelation)
            .where(
                NPCRelation.session_id == session_id,
                NPCRelation.npc_a == npc_name,
            )
            .order_by(NPCRelation.npc_b.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "target": row.npc_b,
                "trust": row.trust,
                "label": row.relationship_label,
                "history_summary": row.history_summary,
            }
            for row in rows
        ]

    async def batch_get_npc_peer_relations(
        self,
        db,
        session_id: str,
        npc_names: list[str],
    ) -> dict[str, list[dict]]:
        """Single-SQL batch version of get_npc_peer_relations.

        Pulls the outgoing relations for ALL ``npc_names`` in one query and
        groups them per asking NPC in Python. Same information-isolation
        contract as the single-NPC version (only npc_a's own outgoing view).
        Returns ``{npc_name: [relation_dict, ...]}``; NPCs with no relations
        get an empty list.
        """
        if not npc_names:
            return {}
        from models.npc_relation import NPCRelation

        stmt = (
            select(NPCRelation)
            .where(
                NPCRelation.session_id == session_id,
                NPCRelation.npc_a.in_(npc_names),
            )
            .order_by(NPCRelation.npc_b.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        by_npc: dict[str, list[dict]] = {n: [] for n in npc_names}
        for row in rows:
            bucket = by_npc.get(row.npc_a)
            if bucket is None:
                continue
            bucket.append(
                {
                    "target": row.npc_b,
                    "trust": row.trust,
                    "label": row.relationship_label,
                    "history_summary": row.history_summary,
                }
            )
        return by_npc

    async def batch_get_npc_recent_utterances(
        self,
        db,
        session_id: str,
        npc_names: list[str],
        limit: int = 3,
    ) -> dict[str, list[str]]:
        """Single-SQL batch version of get_npc_recent_utterances.

        Pulls one window of recent assistant messages ONCE and extracts each
        NPC's most recent utterances from it in Python — instead of every NPC
        re-reading an overlapping window. Returns ``{npc_name: [utterance,
        ...]}`` (newest first, up to ``limit`` each); NPCs with no past
        utterances get an empty list.
        """
        if not npc_names:
            return {}
        from models.game import Message

        # Same absolute candidate window as the single-NPC path: "the most
        # recent N assistant messages" is NPC-independent (every NPC looks at
        # the same window), so batching over one window of this size yields
        # results identical to calling the single-NPC method per NPC.
        candidate_window = max(limit * 4, 8)
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role == "assistant",
                Message.npc_dialogues.is_not(None),
            )
            .order_by(Message.id.desc())
            .limit(candidate_window)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        name_set = set(npc_names)
        out: dict[str, list[str]] = {n: [] for n in npc_names}
        for row in rows:
            if not isinstance(row.npc_dialogues, dict):
                continue
            for name in name_set:
                bucket = out[name]
                if len(bucket) >= limit:
                    continue
                text = row.npc_dialogues.get(name)
                if isinstance(text, str) and text.strip():
                    bucket.append(text.strip())
        return out

    async def get_npc_recent_utterances(
        self,
        db,
        session_id: str,
        npc_name: str,
        limit: int = 3,
    ) -> list[str]:
        """Phase 1.B.4 — return up to ``limit`` of this NPC's most recent raw
        utterances, newest first.

        Pulls a small window of recent assistant messages whose
        ``npc_dialogues`` JSON contains this NPC. Used as a "voice anchor"
        for the NPC system prompt so language and tone stay consistent.
        Returns empty list when no past utterances exist or the column is
        absent on legacy rows.
        """
        from models.game import Message

        # Pull a wider window than ``limit`` because not every recent
        # assistant message will mention this NPC. 4× limit is a cheap upper
        # bound that avoids round-tripping for typical scenes.
        candidate_window = max(limit * 4, 8)
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role == "assistant",
                Message.npc_dialogues.is_not(None),
            )
            .order_by(Message.id.desc())
            .limit(candidate_window)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        utterances: list[str] = []
        for row in rows:
            if not isinstance(row.npc_dialogues, dict):
                continue
            text = row.npc_dialogues.get(npc_name)
            if isinstance(text, str) and text.strip():
                utterances.append(text.strip())
                if len(utterances) >= limit:
                    break
        return utterances

    async def attach_embeddings(self, entries: list[dict]) -> list[dict]:
        """Mutate ``entries`` in-place to add an ``embedding`` field.

        Best-effort: when the embedding service is disabled or fails, every
        entry gets ``embedding=None`` and the memory write proceeds with
        legacy semantics. Returns the same list reference for chaining.
        """
        if not entries:
            return entries
        texts = [str(entry.get("content") or "") for entry in entries]
        vectors = await embed_texts(texts)
        for entry, vec in zip(entries, vectors):
            entry["embedding"] = vec
        return entries

    def build_memory_context(self, entries: list[dict]) -> str:
        if not entries:
            return ""
        return "\n".join(f"- [第{entry['round_number']}轮] {entry['content']}" for entry in entries)

    def search_messages(
        self,
        messages: list[dict],
        keyword: str,
        max_results: int = 3,
    ) -> list[dict]:
        if not keyword:
            return []

        matched = [message for message in messages if keyword in str(message.get("content", ""))]
        matched.sort(key=lambda message: int(message.get("round", 0)), reverse=True)
        return matched[:max_results]

    # -------------------------------------------------------------------------
    # v2 NPC recall helpers (§7.1 NPC Agent injection extension)
    # -------------------------------------------------------------------------

    def find_relevant_lore(
        self,
        npc_knowledge: list[str],
        lore_pack: dict | None,
        *,
        top_k: int = 3,
    ) -> list[dict]:
        """Return up to *top_k* lore content_blocks relevant to this NPC's knowledge.

        Strategy: keyword substring matching between the NPC's knowledge items
        and each content_block's heading + body text.  A score is computed per
        block as the count of knowledge terms that appear in the block text.
        Blocks with score > 0 are returned in descending score order, capped at
        *top_k*.

        TODO: upgrade to embedding cosine similarity via
        ``services/embedding_service.py`` when production embeddings are
        available.
        """
        if not npc_knowledge:
            return []
        if not lore_pack:
            return []
        dimensions: list[dict] = lore_pack.get("dimensions") or []
        if not dimensions:
            return []

        # Build a flat list of query terms from NPC knowledge strings.
        query_terms: list[str] = []
        for item in npc_knowledge:
            text = str(item).strip()
            if text:
                # Simple tokenisation: split on whitespace / punctuation.
                query_terms.extend(t for t in text.split() if t)

        if not query_terms:
            return []

        scored: list[tuple[int, dict]] = []
        for dim in dimensions:
            dim_key = str(dim.get("key") or "")
            dim_name = str(dim.get("name") or "")
            for block in dim.get("content_blocks") or []:
                heading = str(block.get("heading") or "")
                body = str(block.get("body") or "")
                combined = f"{heading} {body}".lower()
                score = sum(1 for kw in query_terms if kw.lower() in combined)
                if score > 0:
                    # Augment block with dimension metadata for prompt rendering.
                    enriched = {
                        "key": dim_key,
                        "name": dim_name,
                        "heading": heading,
                        "body": body,
                        "_score": score,
                    }
                    scored.append((score, enriched))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [block for _, block in scored[:top_k]]

    def find_npc_shared_events(
        self,
        npc_name: str,
        shared_events: list[dict] | None,
    ) -> list[dict]:
        """Return shared_events that involve *npc_name*, from that NPC's perspective.

        Each returned dict has keys: id, title, summary, knows, believes, feels.
        ``perceptions[npc_name]`` is used for knows/believes/feels; other NPCs'
        perceptions are never included (information isolation rule).
        """
        if not shared_events:
            return []

        result: list[dict] = []
        for event in shared_events:
            involved: list[str] = event.get("involved_npcs") or []
            if npc_name not in involved:
                continue
            perceptions: dict = event.get("perceptions") or {}
            npc_perception: dict = perceptions.get(npc_name) or {}
            result.append(
                {
                    "id": str(event.get("id") or ""),
                    "title": str(event.get("title") or ""),
                    "summary": str(event.get("summary") or ""),
                    "knows": str(npc_perception.get("knows") or ""),
                    "believes": str(npc_perception.get("believes") or ""),
                    "feels": str(npc_perception.get("feels") or ""),
                }
            )
        return result

    def find_npc_rumors(
        self,
        npc_name: str,
        events_data: list[dict] | None,
        triggered_event_ids: set[str] | None = None,
    ) -> list[str]:
        """Return rumor texts from *events_data* that this NPC knows about.

        Only untriggered events are considered — once an event fires it is no
        longer a rumour.  Results are deduplicated.
        """
        if not events_data:
            return []

        triggered: set[str] = triggered_event_ids or set()
        seen: set[str] = set()
        result: list[str] = []

        for event in events_data:
            event_id = str(event.get("id") or "")
            if event_id and event_id in triggered:
                continue
            for rumor in event.get("rumors") or []:
                knowers: list[str] = rumor.get("knower_npcs") or []
                if npc_name not in knowers:
                    continue
                text = str(rumor.get("text") or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    result.append(text)

        return result
