from __future__ import annotations
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from quiz.models import Quiz
from .serializers import QuizSerializer, QuizPartialUpdateSerializer
from .utils import validate_youtube_url, create_quiz_from_url
import logging

logger = logging.getLogger(__name__)

class CreateQuizView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        url = (request.data or {}).get("url", "").strip()
        if not validate_youtube_url(url):
            return Response({"detail": "Invalid YouTube URL."}, status=400)
        try:
            quiz = create_quiz_from_url(request.user, url)
            return Response(QuizSerializer(quiz).data, status=201)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception as e:
            logger.exception("createQuiz failed")  # ← stacktrace lands in logs
            return Response({"detail": "Internal Server Error"}, status=500)

class UserQuizzesView(generics.ListAPIView):
    """GET /api/quizzes/ — list current user's quizzes."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuizSerializer

    def get_queryset(self):
        return (
            Quiz.objects.filter(owner=self.request.user)
            .prefetch_related("questions")
            .order_by("-created_at")
        )

class QuizDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET|PATCH|DELETE /api/quizzes/{id}/ — owner-only."""
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return Quiz.objects.filter(owner=self.request.user).prefetch_related("questions")

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return QuizPartialUpdateSerializer
        return QuizSerializer

    def patch(self, request, *args, **kwargs):
        resp = super().patch(request, *args, **kwargs)
        if resp.status_code == status.HTTP_200_OK:
            obj = self.get_object()
            resp.data = QuizSerializer(obj).data
        return resp
