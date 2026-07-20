"""Chunk-packing invariants."""
from mulitaminer2.chunking import count_tokens, pack
from mulitaminer2.models import Block


def _blocks(n: int, size: int = 200) -> list[Block]:
    return [Block(id=i, text=("word " * (size // 5)).strip()) for i in range(n)]


def test_every_block_in_exactly_one_chunk_in_order():
    blocks = _blocks(11)
    chunks, warnings = pack(blocks, max_blocks_per_chunk=4, token_budget=100_000)
    seen = [b.id for c in chunks for b in c.blocks]
    assert seen == list(range(11))
    assert not warnings


def test_max_blocks_per_chunk_respected():
    chunks, _ = pack(_blocks(10), max_blocks_per_chunk=3, token_budget=100_000)
    assert all(len(c.blocks) <= 3 for c in chunks)
    assert len(chunks) == 4  # 3+3+3+1


def test_token_budget_respected():
    blocks = _blocks(8, size=4000)
    budget = 3000
    chunks, _ = pack(blocks, max_blocks_per_chunk=8, token_budget=budget)
    for c in chunks:
        if len(c.blocks) > 1:
            assert c.token_estimate <= budget * 0.85


def test_oversized_block_goes_alone_with_warning():
    big = Block(id=0, text="word " * 5000)
    small = Block(id=1, text="tiny")
    chunks, warnings = pack([big, small], max_blocks_per_chunk=4, token_budget=1000)
    assert [b.id for b in chunks[0].blocks] == [0]
    assert [b.id for b in chunks[1].blocks] == [1]
    assert warnings and "block 0" in warnings[0]


def test_count_tokens_positive_and_monotonic():
    a = count_tokens("hello world")
    b = count_tokens("hello world " * 10)
    assert 0 < a < b
