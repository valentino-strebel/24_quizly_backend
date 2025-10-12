from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .serializers import RegisterSerializer

ACCESS_COOKIE_NAME = getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token')
REFRESH_COOKIE_NAME = getattr(settings, 'JWT_REFRESH_COOKIE_NAME', 'refresh_token')
COOKIE_DOMAIN = getattr(settings, 'JWT_COOKIE_DOMAIN', None)
COOKIE_SECURE = getattr(settings, 'JWT_COOKIE_SECURE', True)
COOKIE_SAMESITE = getattr(settings, 'JWT_COOKIE_SAMESITE', 'Lax')

def set_token_cookies(response, access_token: str, refresh_token: str | None = None):
    # Access cookie
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path='/',
        domain=COOKIE_DOMAIN,
        max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
    )
    # Refresh cookie (optional)
    if refresh_token is not None:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path='/',
            domain=COOKIE_DOMAIN,
            max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        )

def clear_token_cookies(response):
    response.delete_cookie(ACCESS_COOKIE_NAME, path='/', domain=COOKIE_DOMAIN, samesite=COOKIE_SAMESITE)
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/', domain=COOKIE_DOMAIN, samesite=COOKIE_SAMESITE)

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = RegisterSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response({"detail": "User created successfully!"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Validation errors are handled by DRF automatically with 400.
            if hasattr(e, 'detail'):
                raise
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            username = request.data.get('username')
            password = request.data.get('password')

            if not username or not password:
                return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

            user = authenticate(request, username=username, password=password)
            if user is None:
                return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

            refresh = RefreshToken.for_user(user)
            access = str(refresh.access_token)

            update_last_login(None, user)

            resp = Response({
                "detail": "Login successfully!",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                }
            }, status=status.HTTP_200_OK)

            set_token_cookies(resp, access_token=access, refresh_token=str(refresh))
            return resp

        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_cookie = request.COOKIES.get(REFRESH_COOKIE_NAME)
            if not refresh_cookie:
                return Response({"detail": "Not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

            # Blacklist the refresh token
            try:
                token = RefreshToken(refresh_cookie)
                token.blacklist()
            except (TokenError, InvalidToken):
                # Even if invalid, clear cookies and return 200 per spec text
                pass

            resp = Response({
                "detail": "Log-Out successfully! All Tokens will be deleted. Refresh token is now invalid."
            }, status=status.HTTP_200_OK)
            clear_token_cookies(resp)
            return resp

        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CookieTokenRefreshView(APIView):
    """
    Reads refresh token from HttpOnly cookie and returns a new access token.
    Sets a fresh access_token cookie.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            refresh_cookie = request.COOKIES.get(REFRESH_COOKIE_NAME)
            if not refresh_cookie:
                return Response({"detail": "Refresh token missing."}, status=status.HTTP_401_UNAUTHORIZED)

            serializer = TokenRefreshSerializer(data={"refresh": refresh_cookie})
            try:
                serializer.is_valid(raise_exception=True)
            except InvalidToken:
                return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

            access = serializer.validated_data['access']

            resp = Response({
                "detail": "Token refreshed",
                "access": access
            }, status=status.HTTP_200_OK)
            set_token_cookies(resp, access_token=access, refresh_token=None)
            return resp

        except Exception:
            return Response({"detail": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
