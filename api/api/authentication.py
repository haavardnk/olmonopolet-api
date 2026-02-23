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
                decoded_token = auth.verify_id_token(
                    bearer_token, check_revoked=True
                )
            except auth.ExpiredIdTokenError:
                raise exceptions.AuthenticationFailed("ID token has expired")
            except auth.RevokedIdTokenError:
                raise exceptions.AuthenticationFailed("ID token has been revoked")
            except auth.InvalidIdTokenError as e:
                raise exceptions.AuthenticationFailed(f"Invalid ID token: {str(e)}")
            except Exception as e:
                raise exceptions.AuthenticationFailed(
                    f"Authentication failed: {str(e)}"
                )
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
            except auth.InvalidSessionCookieError as e:
                raise exceptions.AuthenticationFailed(f"Invalid session: {str(e)}")
            except Exception as e:
                raise exceptions.AuthenticationFailed(
                    f"Authentication failed: {str(e)}"
                )

        uid: str | None = decoded_token.get("uid")
        email: str | None = decoded_token.get("email")

        if not uid:
            raise exceptions.AuthenticationFailed("Invalid token: missing uid")
        if not email:
            raise exceptions.AuthenticationFailed("Invalid token: missing email")

        user, _ = User.objects.get_or_create(
            email=email, defaults={"username": email}
        )

        return (user, None)
