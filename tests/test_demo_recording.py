from pathlib import Path


def test_demo_recording_is_real_status_capture():
    cast = Path("docs/demo.cast")
    svg = Path("docs/demo.svg")
    assert cast.is_file()
    assert svg.is_file()
    text = cast.read_text(encoding="utf-8")
    assert "openbundle init" in text
    assert "openbundle status" in text
    assert "OpenBundle status" in text
    assert "heuristic (not Lynx)" in text
    assert "rag_faithfulness: Lynx-8B" not in text or "heuristic (not Lynx)" in text
    svg_text = svg.read_text(encoding="utf-8")
    assert "openbundle status" in svg_text
    assert "live" in svg_text or "warming" in svg_text
