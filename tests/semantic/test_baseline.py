"""Tests for the SQLite baseline store."""

import numpy as np
import pytest

from constraint_mcp.semantic.baseline import BaselineStore


@pytest.fixture
def store(tmp_path):
    # nested path also verifies parent-directory creation
    return BaselineStore(tmp_path / "sub" / "baselines.db")


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(384).astype(np.float32)
    return v / np.linalg.norm(v)


class TestBaselineStore:
    def test_missing_returns_none(self, store):
        assert store.get("x.py") is None
        assert store.get_mode("x.py") is None

    def test_set_get_round_trip(self, store):
        v = _vec(1)
        store.set("src/a.py", "content", v, "auto")
        got = store.get("src/a.py")
        assert got is not None
        assert np.allclose(got, v)
        assert store.get_mode("src/a.py") == "auto"

    def test_auto_mode_overwrites(self, store):
        store.set("src/a.py", "v1", _vec(1), "auto")
        store.set("src/a.py", "v2", _vec(2), "auto")
        assert np.allclose(store.get("src/a.py"), _vec(2))

    def test_locked_mode_is_immutable(self, store):
        store.set("src/a.py", "v1", _vec(1), "locked")
        store.set("src/a.py", "v2", _vec(2), "locked")
        assert np.allclose(store.get("src/a.py"), _vec(1))

    def test_count_and_files(self, store):
        store.set("src/b.py", "x", _vec(3), "auto")
        store.set("src/a.py", "y", _vec(4), "auto")
        assert store.count() == 2
        assert store.files() == ["src/a.py", "src/b.py"]  # ordered

    def test_content_hash(self, store):
        assert store.content_hash("hello") == store.content_hash("hello")
        assert store.content_hash("a") != store.content_hash("b")

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "b.db"
        s1 = BaselineStore(path)
        s1.set("src/a.py", "x", _vec(5), "auto")
        s2 = BaselineStore(path)
        assert np.allclose(s2.get("src/a.py"), _vec(5))
