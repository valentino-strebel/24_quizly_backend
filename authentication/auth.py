from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication

class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw = request.COOKIES.get(getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token'))
        if raw:
            validated = self.get_validated_token(raw)
            return (self.get_user(validated), validated)
        return super().authenticate(request)  # fall back to Authorization header
