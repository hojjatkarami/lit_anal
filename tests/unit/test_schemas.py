from app.synthesis.schemas import PaperAnswerOutput


def test_paper_answer_output_schema_valid():
    payload = {
        "paper_id": "paper-1",
        "paper_title": "Test Paper",
        "answers": [
            {
                "question": "What is the method?",
                "answer": "A transformer-based classifier.",
                "evidence": [
                    {
                        "quote": "We use a transformer-based classifier.",
                        "page": 3,
                        "section": "Methods",
                        "figure_id": None,
                    }
                ],
                "references": [
                    {
                        "title": "Test Paper",
                        "year": 2024,
                        "doi": "10.1000/test",
                    }
                ],
                "status": "answered",
            }
        ],
    }
    out = PaperAnswerOutput.model_validate(payload)
    assert out.paper_id == "paper-1"
    assert out.answers[0].status == "answered"
