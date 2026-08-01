from rest_framework.renderers import BrowsableAPIRenderer

PUBLIC_CACHE_SECONDS = 60 * 15


class BrowsableMixin:
    def get_renderers(self) -> list:
        renderers = list(getattr(self, "renderer_classes", []))
        request = getattr(self, "request", None)
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            renderers.append(BrowsableAPIRenderer)
        return [renderer() for renderer in renderers]
