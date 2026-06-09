"""Tests for the fastembed wrapper. Uses real embeddings."""

import numpy as np


class TestEmbeddingEngine:
    def test_shape(self, engine):
        v = engine.embed("authenticate user with a password and jwt token")
        assert v.shape == (384,)

    def test_normalized(self, engine):
        v = engine.embed("some representative source code text")
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5

    def test_cache_returns_same_object(self, engine):
        text = "login authentication password credentials session"
        assert engine.embed(text) is engine.embed(text)

    def test_similar_texts_score_high(self, engine):
        a = engine.embed("login authentication password credentials session jwt")
        b = engine.embed("verify user credentials and issue a session token")
        assert engine.similarity(a, b) > 0.6

    def test_dissimilar_texts_score_lower(self, engine):
        auth = engine.embed("login authentication password credentials session jwt")
        db = engine.embed("execute SQL select query against database cursor rows")
        assert engine.similarity(auth, db) < engine.similarity(
            auth, engine.embed("verify user credentials and issue a session token")
        )
