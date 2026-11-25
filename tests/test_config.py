from app.config import load_config


def test_defaults_without_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    cfg = load_config()
    assert cfg.llm_model == "deepseek-chat"
    assert cfg.llm_base_url == "https://api.deepseek.com"
    assert cfg.llm_api_key == ""


def test_reads_env_values(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-reasoner")
    cfg = load_config()
    assert cfg.llm_api_key == "sk-test"
    assert cfg.llm_model == "deepseek-reasoner"
