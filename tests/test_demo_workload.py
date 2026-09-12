from tests.demo_workload import openai_bodies, prompts


def test_workload_includes_repeats():
    texts = prompts()
    assert texts.count("Explain HTTP caching.") == 2
    assert len(openai_bodies()) == len(texts)
    assert len(texts[0]) > 500
