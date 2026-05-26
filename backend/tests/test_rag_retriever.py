from app.services.reasoning.rag_retriever import _build_where_filter


def test_build_where_filter_for_tenant_only():
    assert _build_where_filter("tenant-1") == {"tenant_id": "tenant-1"}


def test_build_where_filter_for_single_document():
    assert _build_where_filter("tenant-1", ["doc-1"]) == {
        "$and": [{"tenant_id": "tenant-1"}, {"document_id": "doc-1"}]
    }


def test_build_where_filter_for_multiple_documents():
    assert _build_where_filter("tenant-1", ["doc-1", "doc-2"]) == {
        "$and": [{"tenant_id": "tenant-1"}, {"document_id": {"$in": ["doc-1", "doc-2"]}}]
    }
