"""Workflow integration tests with mocked LLM and no database dependency."""

from app.synthesis.workflow import PaperState, _build_graph, _node_answer_questions


class DummySession:
    """Minimal session placeholder used only for graph compilation."""


def test_workflow_graph_compiles():
    graph = _build_graph(session=DummySession(), run_id="run-1")
    assert graph is not None


def test_node_answer_questions_with_mocked_llm(monkeypatch):
    class FakeUsage:
        prompt_tokens = 7
        completion_tokens = 11

    class FakeMessage:
        content = (
            '{"paper_id":"p1","paper_title":"Title","answers":['
            '{"question":"What is the method?","answer":"Method X",'
            '"evidence":[],"references":[],"status":"answered"}]}'
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = FakeUsage()

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeResponse()

    monkeypatch.setattr("app.synthesis.workflow._get_llm_client", lambda: FakeClient())

    state: PaperState = {
        "paper_id": "p1",
        "run_id": "r1",
        "questions": ["What is the method?"],
        "text_content": "Some extracted text",
        "paper_title": "Title",
        "output": None,
        "error": None,
    }

    out = _node_answer_questions(state)
    assert out["error"] is None
    assert out["output"] is not None
    assert out["output"].answers[0].answer == "Method X"
