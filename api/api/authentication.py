from __future__ import annotations

from django.contrib.auth import get_user_model
from firebase_admin import auth
from rest_framework import authentication, exceptions

User = get_user_model()


class FirebaseAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        session_cookie = request.COOKIES.get("session")

        if not session_cookie:
            return None

        try:
            decoded_token = auth.verify_session_cookie(
                session_cookie, check_revoked=True
            )
            uid = decoded_token.get("uid")
            email = decoded_token.get("email")

            if not uid:
                raise exceptions.AuthenticationFailed("Invalid session: missing uid")

            if not email:
                raise exceptions.AuthenticationFailed("Invalid session: missing email")

            user, created = User.objects.get_or_create(
                email=email, defaults={"username": email}
            )

            return (user, None)

        except auth.ExpiredSessionCookieError:
            raise exceptions.AuthenticationFailed("Session has expired")

        except auth.RevokedSessionCookieError:
            raise exceptions.AuthenticationFailed("Session has been revoked")

        except auth.InvalidSessionCookieError as e:
            raise exceptions.AuthenticationFailed(f"Invalid session: {str(e)}")

        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Authentication failed: {str(e)}")
