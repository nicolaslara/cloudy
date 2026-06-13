from cloudy.core.cache import MemoryCache
from cloudy.geocode import Candidate, cached_search


def test_memory_cache_ttl_and_lru() -> None:
    now = [0.0]
    cache = MemoryCache(maxsize=2, clock=lambda: now[0])

    cache.set("a", "1", ttl_s=10)
    assert cache.get("a") == "1"

    now[0] = 11.0  # past TTL
    assert cache.get("a") is None

    cache.set("a", "1", ttl_s=100)
    cache.set("b", "2", ttl_s=100)
    cache.get("a")  # refresh a's recency
    cache.set("c", "3", ttl_s=100)  # evicts b (least recently used)
    assert cache.get("a") == "1"
    assert cache.get("b") is None
    assert cache.get("c") == "3"


def test_cached_search_calls_fetch_once(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import cloudy.geocode as geocode_module

    cache = MemoryCache()
    monkeypatch.setattr(geocode_module, "get_cache", lambda: cache)

    calls = 0

    def fetch() -> list[Candidate]:
        nonlocal calls
        calls += 1
        return [Candidate(label="Storgatan 2, Umeå", lat=63.8, lon=20.3)]

    first = cached_search("photon", "storgatan 2", 6, fetch)
    second = cached_search("photon", "storgatan 2", 6, fetch)
    assert calls == 1
    assert first == second
    assert second[0].label == "Storgatan 2, Umeå"
