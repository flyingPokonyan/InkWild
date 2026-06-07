from services.tavily_search import DEFAULT_TIMEOUT, TavilySearch


def test_tavily_default_timeout_is_100_seconds():
    assert DEFAULT_TIMEOUT == 100.0
    assert TavilySearch().timeout == 100.0
