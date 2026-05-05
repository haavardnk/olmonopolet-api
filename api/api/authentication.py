from __future__ import annotations

from django.contrib.auth import get_user_model
from firebase_admin import auth
from rest_framework import authentication, exceptions

User = get_user_model()


class FirebaseAuthentication(authentication.BaseAuthentication):
    def _get_bearer_token(self, request) -> str | None:
        auth_header: str = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    def authenticate(self, request) -> tuple[User, None] | None:
        bearer_token = self._get_bearer_token(request)

        if bearer_token:
            try:
                decoded_token = auth.verify_id_token(bearer_token, check_revoked=True)
            except auth.ExpiredIdTokenError:
                raise exceptions.AuthenticationFailed("ID token has expired")
            except auth.RevokedIdTokenError:
                raise exceptions.AuthenticationFailed("ID token has been revoked")
            except auth.InvalidIdTokenError:
                raise exceptions.AuthenticationFailed("Invalid ID token")
            except Exception:
                raise exceptions.AuthenticationFailed("Authentication failed")
        else:
            session_cookie = request.COOKIES.get("session")
            if not session_cookie:
                return None
            try:
                decoded_token = auth.verify_session_cookie(
                    session_cookie, check_revoked=True
                )
            except auth.ExpiredSessionCookieError:
                raise exceptions.AuthenticationFailed("Session has expired")
            except auth.RevokedSessionCookieError:
                raise exceptions.AuthenticationFailed("Session has been revoked")
            except auth.InvalidSessionCookieError:
                raise exceptions.AuthenticationFailed("Invalid session")
            except Exception:
                raise exceptions.AuthenticationFailed("Authentication failed")

        uid: str | None = decoded_token.get("uid")
        email: str | None = decoded_token.get("email")

        if not uid:
            raise exceptions.AuthenticationFailed("Invalid token")
        if not email:
            raise exceptions.AuthenticationFailed("Invalid token")

        user, _ = User.objects.get_or_create(email=email, defaults={"username": email})

        return (user, None)
