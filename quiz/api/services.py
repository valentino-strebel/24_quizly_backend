import re
from typing import Tuple, List, Dict
from quiz.models import Quiz, Question

_YT_REGEX = re.compile(
    r'^(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})'
)

def _extract_video_id(url: str) -> str | None:
    m = _YT_REGEX.match(url.strip())
    return m.group(1) if m else None

def validate_youtube_url(url: str) -> bool:
    return _extract_video_id(url) is not None

def generate_quiz_from_youtube_url(owner, url: str) -> Tuple[Quiz, List[Question]]:
    """
    Placeholder generator: makes a simple but valid quiz without external calls.
    Swap this with a real transcript→Q/A pipeline when ready.
    """
    vid = _extract_video_id(url) or 'unknown'

    title = f'Quiz for {vid}'
    description = 'Auto-generated quiz.'
    questions_data: List[Dict] = [
        {
            "question_title": "What is the main idea of the video?",
            "question_options": ["Option A", "Option B", "Option C", "Option D"],
            "answer": "Option A",
        }
    ]

    quiz = Quiz.objects.create(
        owner=owner,
        title=title,
        description=description,
        video_url=url,
    )
    questions = []
    for qd in questions_data:
        questions.append(Question.objects.create(
            quiz=quiz,
            question_title=qd["question_title"],
            question_options=qd["question_options"],
            answer=qd["answer"],
        ))
    return quiz, questions
