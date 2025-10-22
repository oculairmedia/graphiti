from graphiti_core.utils.maintenance.node_operations import merge_edge_properties


def test_merge_edge_properties_drops_empty_fact_embedding():
    existing = {}
    incoming = {"fact": "Alice met Bob", "fact_embedding": []}

    merged = merge_edge_properties(existing, incoming)

    assert (
        merged.get("fact_embedding") is None
    ), "Empty fact embeddings should be sanitized to None to avoid Falkor vector errors"
