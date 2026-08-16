import json

import pytest

from ranks_api.snapshot import (
    build_index,
    decode_cursor,
    encode_cursor,
    page_items,
    ranking_page,
)


SAMPLE = {
    "generated_at": "2026-08-15T00:00:00+00:00",
    "sources": [{"name": "src", "ok": True}],
    "models": {"a": {}, "b": {}, "n/a": {}},
    "mentions": {"CRAG": []},
    "emerging_models": [{"id": f"m{i}", "name": f"M{i}"} for i in range(30)],
    "benchmarks": [
        {
            "id": "open-llm-leaderboard",
            "name": "Hugging Face Open LLM Leaderboard",
            "url": "https://example.test/hf",
            "category": "research",
            "rankings": [
                {
                    "model_id": "dup/model",
                    "name": "Dup",
                    "rank": 1,
                    "score": 99,
                    "source": "hf",
                    "parse_date": "2026-08-01",
                },
                {
                    "model_id": "dup/model",
                    "name": "Dup copy",
                    "rank": 2,
                    "score": 90,
                    "source": "hf",
                    "parse_date": "2026-08-01",
                },
                {
                    "model_id": "other/model",
                    "name": "Other",
                    "rank": 3,
                    "score": 80,
                    "source": "hf",
                    "parse_date": "2026-08-02",
                },
                *[
                    {
                        "model_id": f"row/{i}",
                        "name": f"Row {i}",
                        "rank": i,
                        "score": 70 - i,
                        "source": "hf",
                        "parse_date": "2026-08-03",
                    }
                    for i in range(4, 12)
                ],
            ],
        },
        {
            "id": "gaia",
            "name": "GAIA",
            "url": "https://example.test/gaia",
            "category": "planning",
            "rankings": [{"model_id": "x", "name": "X", "rank": 1, "score": 1}],
        },
    ],
    "categories": [
        {
            "id": "research",
            "name": "Research",
            "description": "research models",
            "benchmarks": ["open-llm-leaderboard", "open-llm-leaderboard"],
            "quality_ranked": [
                {"id": "m1", "name": "M1", "quality": 100, "price_source": "catalog"},
                {"id": "m2", "name": "M2", "quality": 90, "price_source": "catalog"},
                {"id": "m3", "name": "M3", "quality": 80, "price_source": "catalog"},
                {"id": "m4", "name": "M4", "quality": 70, "price_source": "catalog"},
                {"id": "m5", "name": "M5", "quality": 60, "price_source": "catalog"},
                {"id": "m6", "name": "M6", "quality": 50, "price_source": "catalog"},
            ],
            "benchmark_details": [
                {
                    "id": "open-llm-leaderboard",
                    "name": "Hugging Face Open LLM Leaderboard",
                    "rankings": [{"model_id": "should-not-duplicate", "rank": 1}],
                }
            ],
        }
    ],
}


def test_homepage_drops_duplicates_and_catalog():
    index = build_index(SAMPLE)
    home = index.homepage
    assert "models" not in home
    assert "mentions" not in home
    assert home["model_count"] == 3
    assert len(home["benchmarks"]) == 2
    assert len(home["categories"]) == 1
    cat = home["categories"][0]
    assert cat["benchmarks"] == [
        {"id": "open-llm-leaderboard", "name": "Hugging Face Open LLM Leaderboard"}
    ]
    assert "benchmark_details" not in cat
    assert len(cat["quality_ranked"]) == 5
    assert cat["quality_total"] == 6
    assert decode_cursor(cat["next_cursor"])["m"] == "m5"
    bench = home["benchmarks"][0]
    assert bench["rankings_total"] == 10  # 11 rows minus 1 duplicate
    assert len(bench["rankings"]) == 5
    assert decode_cursor(bench["next_cursor"])["m"] == "row/6"
    parsed = json.loads(index.homepage_json)
    assert parsed["model_count"] == 3
    assert index.etag.startswith('"')
    assert index.etag.endswith('"')


def test_cursor_iterator_walks_full_list_without_overlap():
    index = build_index(SAMPLE)
    list_id = "benchmark:open-llm-leaderboard"
    cursor = None
    seen: list[str] = []
    pages = 0
    while True:
        page = ranking_page(index, list_id, cursor, limit=4)
        pages += 1
        ids = [str(row["model_id"]) for row in page["items"]]
        assert not set(ids) & set(seen)
        seen.extend(ids)
        if page["next_cursor"] is not None:
            payload = decode_cursor(page["next_cursor"])
            assert payload["m"] == ids[-1]
            assert payload["src"] == "hf"
            assert "d" in payload
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert len(seen) == 10
    assert seen[0] == "dup/model"


def test_keyset_is_not_an_offset():
    items = [
        {"id": "a", "score": 2, "source": "s", "parse_date": "2026-01-01"},
        {"id": "b", "score": 1, "source": "s", "parse_date": "2026-01-02"},
    ]
    page = page_items(items, None, 1)
    assert page["items"][0]["id"] == "a"
    payload = decode_cursor(page["next_cursor"])
    assert payload == {
        "m": "a",
        "src": "s",
        "d": "2026-01-01",
        "q": None,
        "sc": 2.0,
        "r": None,
    }
    page2 = page_items(items, page["next_cursor"], 1)
    assert page2["items"][0]["id"] == "b"
    assert page2["next_cursor"] is None
    with pytest.raises(ValueError, match="keyset"):
        page_items(items, "1", 1)


def test_encode_roundtrip_uses_row_identity():
    row = {
        "model_id": "openai/gpt-5",
        "quality": 88.0,
        "source": "lmarena",
        "parse_date": "2026-08-10",
        "rank": 1,
    }
    cursor = encode_cursor(row)
    assert decode_cursor(cursor)["m"] == "openai/gpt-5"
    assert decode_cursor(cursor)["src"] == "lmarena"
    assert decode_cursor(cursor)["d"] == "2026-08-10"
