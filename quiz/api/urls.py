from django.urls import path
from .views import CreateQuizView, UserQuizzesView, QuizDetailView

urlpatterns = [
    path('createQuiz/', CreateQuizView.as_view(), name='create_quiz'),
    path('quizzes/', UserQuizzesView.as_view(), name='user_quizzes'),
    path('quizzes/<int:id>/', QuizDetailView.as_view(), name='quiz_detail'),
]
