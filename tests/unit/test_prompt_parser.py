from app.synthesis.schemas import parse_questions


def test_parse_questions_numbered_list():
    prompt = """1. What is the dataset?\n2. What model is used?\n3. What are limitations?"""
    out = parse_questions(prompt)
    assert len(out) == 3
    assert out[0] == "What is the dataset?"


def test_parse_questions_line_questions():
    prompt = "What is the method?\nWhat are results?"
    out = parse_questions(prompt)
    assert out == ["What is the method?", "What are results?"]


def test_parse_questions_fallback_single():
    prompt = "Summarize the key contribution"
    out = parse_questions(prompt)
    assert out == ["Summarize the key contribution"]
