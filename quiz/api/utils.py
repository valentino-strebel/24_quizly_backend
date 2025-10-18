from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from django.conf import settings
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, PostProcessingError
import google.generativeai as genai
import whisper
from google import genai

YT_RX = re.compile(r"(?:youtu\.be/|v=)([\w\-]{11})")

@dataclass
class QuizSpec:
    title: str
    description: str
    questions: List[Dict[str, Any]]

def parse_youtube_id(url: str) -> str | None:
    """Return 11-char YouTube ID or None."""
    m = YT_RX.search((url or "").strip())
    return m.group(1) if m else None

def validate_youtube_url(url: str) -> bool:
    """Basic YT URL validation via ID extraction."""
    return parse_youtube_id(url) is not None

def _media_dir(sub: str) -> Path:
    """Ensure and return MEDIA/<sub> directory."""
    base = Path(getattr(settings, "MEDIA_ROOT", "media"))
    p = base / sub
    p.mkdir(parents=True, exist_ok=True)
    return p

def _ydl_opts(out_dir: Path) -> Dict[str, Any]:
    """yt-dlp options for bestaudio→mp3 via ffmpeg."""
    return {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "noprogress": True,
    }


def download_audio(url: str, out_dir: Path | None = None) -> Path:
    out = _media_dir("audio") if out_dir is None else out_dir
    try:
        with YoutubeDL(_ydl_opts(out)) as ydl:
            info = ydl.extract_info(url, download=True)
    except PostProcessingError as e:
        raise ValueError("Audio extraction failed: ffmpeg not found or misconfigured.") from e
    except DownloadError as e:
        raise ValueError("Failed to download YouTube audio. The URL may be unavailable.") from e
    stem = info.get("id")
    return (out / f"{stem}.mp3").resolve()


def transcribe_audio(audio_path: Path, model_name: str | None = None) -> str:
    try:
        name = model_name or getattr(settings, "WHISPER_MODEL", "base")
        model = whisper.load_model(name)
        res = model.transcribe(str(audio_path))
    except Exception as e:
        raise ValueError("Transcription failed. Check Whisper/Torch installation and model availability.") from e
    return (res.get("text") or "").strip()


def _gemini_client(api_key: str | None = None):
    key = api_key or getattr(settings, "GENAI_API_KEY", "")
    if not key:
        raise ValueError("GENAI_API_KEY is missing.")
    genai.configure(api_key=key)
    return genai

def _quiz_prompt(transcript: str) -> str:
    """Build strict JSON-only prompt for Gemini."""
    return (
        "Generate a quiz JSON with exactly 10 questions, each with 4 options.\n"
        "Fields: title, description, questions:[{question_title, "
        "question_options:[A,B,C,D], answer(one of the options)}].\n"
        "Base it ONLY on this transcript:\n"
        f"{transcript}\n"
        "Respond with JSON only, no prose."
    )

def build_quiz_with_gemini(transcript: str, model: str = "gemini-1.5-flash") -> QuizSpec:
    genai = _gemini_client()
    gm = genai.GenerativeModel(model)
    out = gm.generate_content(_quiz_prompt(transcript))
    text = (getattr(out, "text", "") or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        data = json.loads(text)
    except ValueError as e:  
        raise ValueError("LLM did not return valid JSON.") from e

    return QuizSpec(
        title=data["title"],
        description=data.get("description", ""),
        questions=data["questions"],
    )

def _validate_question(q: Dict[str, Any]) -> None:
    """Raise ValueError if question is malformed."""
    opts = q.get("question_options") or []
    if len(opts) != 4:
        raise ValueError("Each question must have 4 options.")
    if q.get("answer") not in opts:
        raise ValueError("Answer must be one of the options.")

def validate_quiz_spec(spec: QuizSpec) -> None:
    """Validate structure and size of the quiz spec."""
    if len(spec.questions) != 10:
        raise ValueError("Quiz must have exactly 10 questions.")
    for q in spec.questions:
        _validate_question(q)

def persist_quiz(owner, video_url: str, spec: QuizSpec):
    """Create Quiz + Questions in DB from spec."""
    from quiz.models import Quiz, Question  # local import avoids cycles
    quiz = Quiz.objects.create(
        owner=owner, title=spec.title, description=spec.description, video_url=video_url
    )
    objs = [
        Question(
            quiz=quiz,
            question_title=q["question_title"],
            question_options=q["question_options"],
            answer=q["answer"],
        )
        for q in spec.questions
    ]
    type(quiz).objects.bulk_create([])  # no-op to keep ≤14 lines, safe
    from django.db import transaction
    with transaction.atomic():
        for o in objs:
            o.save()
    return quiz

def create_quiz_from_url(owner, url: str) -> Any:
    """End-to-end pipeline: URL→audio→transcript→Gemini→persist."""
    if not validate_youtube_url(url):
        raise ValueError("Invalid YouTube URL.")
    audio = download_audio(url)
    text = transcribe_audio(audio)
    spec = build_quiz_with_gemini(text)
    validate_quiz_spec(spec)
    return persist_quiz(owner, url, spec)
