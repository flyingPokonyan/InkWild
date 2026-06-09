"""Provider/transport failures (402 insufficient balance, auth, exhausted
fallback) must surface as a distinct upstream error — NOT be swallowed into a
``llm_parse`` "导演无法解析" parse failure. A stream-level exception is always
upstream; a genuine parse failure is the separate "no valid output" path."""

import pytest

from engine.director_agent import DirectorAgent, DirectorUpstreamError

pytestmark = pytest.mark.asyncio


class _RaisingJsonRouter:
    """stream_json raises before yielding — mimics the router re-raising the
    last provider error (e.g. 402) after exhausting the fallback chain."""

    def __init__(self, exc):
        self._exc = exc

    async def stream_json(self, **kwargs):
        if False:  # make this an async generator
            yield {}
        raise self._exc


async def test_json_mode_reraises_upstream_error_instead_of_none():
    class Boom(RuntimeError):
        status_code = 402

    agent = DirectorAgent(_RaisingJsonRouter(Boom("402 Insufficient Balance")))

    with pytest.raises(DirectorUpstreamError):
        await agent._run_json_mode_raw(
            system="s",
            messages=[{"role": "user", "content": "x"}],
            schema={"type": "object"},
        )
