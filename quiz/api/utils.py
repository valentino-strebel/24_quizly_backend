from __future__ import annotations
"""
Quiz creation pipeline

This module downloads audio from a YouTube URL, transcribes it with Whisper,
asks Gemini to generate a quiz JSON, validates it, and persists the result.

It includes JSdoc-equivalent docstrings with clear Args/Returns/Raises
sections and splits long functions into smaller helpers for readability and
testability.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from django.conf import settings
from django.db import transaction

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, PostProcessingError
import google.generativeai as genai
import whisper

# -- Constants -----------------------------------------------------------------

YT_RX = re.compile(r"(?:youtu\.be/|v=)([\w\-]{11})")


# -- Data models ----------------------------------------------------------------

@dataclass
class QuizSpec:
    """In-memory representation of a quiz.

    Attributes:
        title: Quiz title.
        description: Short description of the quiz context.
        questions: A list of question dicts with keys:
            - question_title (str)
            - question_options (List[str]) of length 4
            - answer (str) which must be one of question_options
    """

    title: str
    description: str
    questions: List[Dict[str, Any]]


class QuizQuestion(TypedDict):
    """TypedDict for an individual quiz question."""

    question_title: str
    question_options: List[str]
    answer: str


class QuizSchema(TypedDict):
    """TypedDict for the full quiz JSON schema."""

    title: str
    description: str
    questions: List[QuizQuestion]


# -- URL parsing ----------------------------------------------------------------

def parse_youtube_id(url: str) -> str | None:
    """Extract the 11-character YouTube video ID.

    Args:
        url: A YouTube watch/shortened URL string.

    Returns:
        The 11-character video ID if found, otherwise ``None``.
    """

    m = YT_RX.search((url or "").strip())
    return m.group(1) if m else None


def validate_youtube_url(url: str) -> bool:
    """Quick validation for a YouTube URL via ID extraction.

    Args:
        url: Candidate YouTube URL.

    Returns:
        ``True`` if an ID can be extracted, otherwise ``False``.
    """

    return parse_youtube_id(url) is not None


# -- Filesystem helpers ---------------------------------------------------------

def _media_dir(sub: str) -> Path:
    """Return a subdirectory in MEDIA_ROOT, creating it if needed.

    Args:
        sub: Subdirectory name relative to MEDIA_ROOT.

    Returns:
        Absolute ``Path`` to the created/existing directory.

    Raises:
        ValueError: If the directory cannot be created.
    """

    try:
        base = Path(getattr(settings, "MEDIA_ROOT", "media"))
        p = base / sub
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception as e:  # pragma: no cover - bubble up
        raise ValueError(f"Cannot prepare media directory: {e}") from e


def _ydl_opts(out_dir: Path) -> Dict[str, Any]:
    """Options for yt-dlp to fetch best audio and convert to MP3 via ffmpeg.

    Args:
        out_dir: Directory where the file should be saved.

    Returns:
        A dict of yt-dlp options.
    """

    return {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "noprogress": True,
    }


# -- Downloading ----------------------------------------------------------------

def _extract_download_info(url: str, out: Path) -> Dict[str, Any]:
    """Run yt-dlp and return the extracted info dict.

    Args:
        url: The YouTube URL to download.
        out: Output directory.

    Returns:
        The info dict from yt-dlp with keys like ``id`` and ``ext``.

    Raises:
        ValueError: If ffmpeg is missing/misconfigured or the download fails.
    """

    try:
        with YoutubeDL(_ydl_opts(out)) as ydl:
            return ydl.extract_info(url, download=True)
    except PostProcessingError as e:
        raise ValueError(
            "Audio extraction failed: ffmpeg not found or misconfigured."
        ) from e
    except DownloadError as e:
        raise ValueError(
            "Failed to download YouTube audio. The URL may be unavailable."
        ) from e


def _audio_path_from_info(info: Dict[str, Any], out: Path) -> Path:
    """Compute the final MP3 path from a yt-dlp info dict.

    Args:
        info: The yt-dlp info dict.
        out: The output directory.

    Returns:
        Absolute path to the resulting MP3 file.
    """

    stem = info.get("id")
    return (out / f"{stem}.mp3").resolve()


def download_audio(url: str, out_dir: Path | None = None) -> Path:
    """Download a YouTube video's audio and return the MP3 file path.

    Args:
        url: The YouTube URL.
        out_dir: Optional existing output directory. Defaults to MEDIA_ROOT/audio.

    Returns:
        Absolute path to the downloaded MP3 file.

    Raises:
        ValueError: When download or post-processing fails.
    """

    out = _media_dir("audio") if out_dir is None else out_dir
    info = _extract_download_info(url, out)
    return _audio_path_from_info(info, out)


# -- Transcription ---------------------------------------------------------------

def transcribe_audio(audio_path: Path, model_name: str | None = None) -> str:
    """Transcribe an audio file using OpenAI Whisper.

    Args:
        audio_path: Path to the MP3 file to transcribe.
        model_name: Whisper model name. Defaults to ``settings.WHISPER_MODEL``
            or ``"base"`` when unset.

    Returns:
        The transcription text (stripped).

    Raises:
        ValueError: If Whisper/Torch is not available or the model load fails.
    """

    try:
        name = model_name or getattr(settings, "WHISPER_MODEL", "base")
        model = whisper.load_model(name)
        res = model.transcribe(str(audio_path))
    except Exception as e:  # pragma: no cover - surface as user error
        raise ValueError(
            "Transcription failed. Check Whisper/Torch installation and model availability."
        ) from e
    return (res.get("text") or "").strip()


# -- Gemini client & prompting ---------------------------------------------------

def _gemini_client(api_key: str | None = None):
    """Configure and return the Gemini client module.

    Args:
        api_key: Optional API key. Uses ``settings.GENAI_API_KEY`` if omitted.

    Returns:
        The configured :mod:`google.generativeai` module.

    Raises:
        ValueError: If no API key is available.
    """

    key = api_key or getattr(settings, "GENAI_API_KEY", "")
    if not key:
        raise ValueError("GENAI_API_KEY is missing.")
    genai.configure(api_key=key)
    return genai


def _quiz_prompt(transcript: str) -> str:
    """Build a strict JSON-only prompt for Gemini based on a transcript.

    Args:
        transcript: The source transcript text used to build quiz questions.

    Returns:
        A system/user prompt instructing Gemini to produce only JSON.
    """

    return (
        "Generate a quiz JSON with exactly 10 questions, each with 4 options.\n"
        "Fields: title, description, questions:[{question_title, "
        "question_options:[A,B,C,D], answer(one of the options)}].\n"
        "Base it ONLY on this transcript:\n"
        f"{transcript}\n"
        "Respond with JSON only, no prose."
    )


def _gemini_generate_json(transcript: str, model: str) -> str:
    """Call Gemini and return the raw JSON text.

    Args:
        transcript: Transcript on which to base the quiz.
        model: Gemini model name, e.g. ``"gemini-2.5-flash"``.

    Returns:
        The raw text returned by the model.

    Raises:
        ValueError: When the upstream call fails or returns empty content.
    """

    genai_mod = _gemini_client()
    gm = genai_mod.GenerativeModel(model)
    try:
        out = gm.generate_content(
            _quiz_prompt(transcript),
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": QuizSchema,
            },
        )
    except Exception as e:  # pragma: no cover - surface as user error
        raise ValueError(f"Quiz generation upstream error: {e}") from e

    text = (getattr(out, "text", "") or "").strip()
    if not text:
        raise ValueError("LLM returned no content.")
    return text


def _parse_quiz_json(text: str) -> QuizSpec:
    """Parse LLM-returned JSON into a ``QuizSpec``.

    Args:
        text: JSON string representing the quiz.

    Returns:
        A validated ``QuizSpec`` instance.

    Raises:
        ValueError: If the JSON cannot be parsed or is missing fields.
    """

    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError("LLM did not return valid JSON.") from e

    return QuizSpec(
        title=data["title"],
        description=data.get("description", ""),
        questions=data["questions"],
    )


def build_quiz_with_gemini(transcript: str, model: str = "gemini-2.5-flash") -> QuizSpec:
    """Generate a quiz from a transcript using Gemini.

    Args:
        transcript: Transcript text for question generation.
        model: Gemini model name. Defaults to ``"gemini-2.5-flash"``.

    Returns:
        A ``QuizSpec`` built from the model's JSON output.

    Raises:
        ValueError: If the upstream call fails or returns invalid JSON.
    """

    raw = _gemini_generate_json(transcript, model)
    return _parse_quiz_json(raw)


# -- Validation -----------------------------------------------------------------

def _validate_question(q: Dict[str, Any]) -> None:
    """Validate a single question dict.

    Args:
        q: A mapping with ``question_options`` and ``answer`` fields.

    Raises:
        ValueError: If the question doesn't have exactly 4 options or if the
        answer isn't one of those options.
    """

    opts = q.get("question_options") or []
    if len(opts) != 4:
        raise ValueError("Each question must have 4 options.")
    if q.get("answer") not in opts:
        raise ValueError("Answer must be one of the options.")


def validate_quiz_spec(spec: QuizSpec) -> None:
    """Validate structure and size of the quiz.

    Args:
        spec: The quiz specification to validate.

    Raises:
        ValueError: If there are not exactly 10 questions or any question is
        malformed.
    """

    if len(spec.questions) != 10:
        raise ValueError("Quiz must have exactly 10 questions.")
    for q in spec.questions:
        _validate_question(q)


# -- Persistence ----------------------------------------------------------------

def _create_quiz(owner: Any, video_url: str, spec: QuizSpec):
    """Create and return a ``Quiz`` ORM instance (unsaved questions).

    Args:
        owner: The user/owner to associate with the quiz.
        video_url: Source YouTube URL.
        spec: The quiz spec providing title/description.

    Returns:
        The created ``Quiz`` instance.
    """

    from quiz.models import Quiz

    return Quiz.objects.create(
        owner=owner, title=spec.title, description=spec.description, video_url=video_url
    )


def _bulk_create_questions(quiz: Any, questions: List[Dict[str, Any]]) -> None:
    """Create all ``Question`` rows for a quiz in bulk.

    Args:
        quiz: The parent ``Quiz`` ORM instance.
        questions: A list of question dicts.
    """

    from quiz.models import Question

    objs = [
        Question(
            quiz=quiz,
            question_title=q["question_title"],
            question_options=q["question_options"],
            answer=q["answer"],
        )
        for q in questions
    ]
    Question.objects.bulk_create(objs)


def persist_quiz(owner: Any, video_url: str, spec: QuizSpec):
    """Persist a quiz and its questions transactionally.

    Args:
        owner: The user/owner to associate with the quiz.
        video_url: Source YouTube URL used to generate the quiz.
        spec: The validated quiz specification.

    Returns:
        The created ``Quiz`` ORM instance.
    """

    with transaction.atomic():
        quiz = _create_quiz(owner, video_url, spec)
        _bulk_create_questions(quiz, spec.questions)
    return quiz


# -- Orchestration --------------------------------------------------------------

def create_quiz_from_url(owner: Any, url: str) -> Any:
    """End-to-end pipeline: URL → audio → transcript → Gemini → persist.

    Args:
        owner: The user/owner to associate with the quiz.
        url: A YouTube URL.

    Returns:
        The created ``Quiz`` ORM instance.

    Raises:
        ValueError: If the URL is invalid, download/transcription fails,
        quiz generation fails, or validation fails.
    """

    if not validate_youtube_url(url):
        raise ValueError("Invalid YouTube URL.")

    audio = download_audio(url)
    text = transcribe_audio(audio)
    spec = build_quiz_with_gemini(text)
    validate_quiz_spec(spec)
    return persist_quiz(owner, url, spec)
