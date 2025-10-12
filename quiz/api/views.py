from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from quiz.models import Quiz
from quiz.permissions import IsOwner
from .serializers import QuizSerializer, QuizPartialUpdateSerializer
from .services import validate_youtube_url, generate_quiz_from_youtube_url

class CreateQuizView(APIView):
    """
    POST /api/createQuiz/
    Auth required. Body: {"url": "<youtube-url>"}
    Returns 201 with the created quiz (nested questions).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            url = (request.data or {}).get('url', '').strip()
            if not url or not validate_youtube_url(url):
                return Response({"detail": "Invalid YouTube URL."}, status=status.HTTP_400_BAD_REQUEST)

            quiz, _ = generate_quiz_from_youtube_url(request.user, url)
            data = QuizSerializer(quiz).data
            return Response(data, status=status.HTTP_201_CREATED)
        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserQuizzesView(APIView):
    """
    GET /api/quizzes/  -> list current user's quizzes (with nested questions)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            qs = Quiz.objects.filter(owner=request.user).prefetch_related('questions')
            data = QuizSerializer(qs, many=True).data
            return Response(data, status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class QuizDetailView(APIView):
    """
    GET /api/quizzes/{id}/
    PATCH /api/quizzes/{id}/
    DELETE /api/quizzes/{id}/
    Only the owner may access/modify/delete.
    """
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_object(self, request, pk):
        quiz = get_object_or_404(Quiz.objects.select_related('owner').prefetch_related('questions'), pk=pk)
        # Object-level permission check (403 if not owner)
        self.check_object_permissions(request, quiz)
        return quiz

    def get(self, request, id):
        try:
            quiz = self.get_object(request, id)
            return Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)
        except Quiz.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except permissions.PermissionDenied:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, id):
        try:
            quiz = self.get_object(request, id)
            serializer = QuizPartialUpdateSerializer(quiz, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            # Return full representation (with nested questions)
            return Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)
        except permissions.PermissionDenied:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        except Quiz.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, id):
        try:
            quiz = self.get_object(request, id)
            quiz.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except permissions.PermissionDenied:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        except Quiz.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
