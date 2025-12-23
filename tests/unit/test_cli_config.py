import os

import pytest

from src.cli import _apply_config
from src.utils.index_manager import get_index_manager


def test_apply_config_updates_env_and_index(monkeypatch):
    manager = get_index_manager()
    manager.configure(alpha=0.5)

    for key in [
        "SILICONFLOW_BASE",
        "SILICONFLOW_MODEL",
        "SILICONFLOW_EMBED_MODEL",
        "SILICONFLOW_RERANK_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = {
        "retrieval": {"alpha": 0.75},
        "siliconflow": {
            "base": "https://alt.siliconflow.cn/v1",
            "chat_model": "Qwen/Qwen3-Next-80B-A3B-Instruct",
            "embed_model": "BAAI/bge-m3",
            "rerank_model": "Qwen/Qwen3-Reranker-4B",
        },
    }

    _apply_config(config)

    assert manager.alpha == 0.75
    assert os.environ["SILICONFLOW_BASE"] == "https://alt.siliconflow.cn/v1"
    assert os.environ["SILICONFLOW_MODEL"] == "Qwen/Qwen3-Next-80B-A3B-Instruct"
    assert os.environ["SILICONFLOW_EMBED_MODEL"] == "BAAI/bge-m3"
    assert os.environ["SILICONFLOW_RERANK_MODEL"] == "Qwen/Qwen3-Reranker-4B"

    for key in [
        "SILICONFLOW_BASE",
        "SILICONFLOW_MODEL",
        "SILICONFLOW_EMBED_MODEL",
        "SILICONFLOW_RERANK_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

