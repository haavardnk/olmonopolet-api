from __future__ import annotations

import json as _json

from django.db import models
from django.db.models import Case, Max, QuerySet, Value, When
from django_q.tasks import async_task
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from beers.api.views.base import BrowsableMixin
from beers.api.serializers import (
    ItemReorderSerializer,
    ListReorderSerializer,
    SharedUserListSerializer,
    UntappdListSearchResultSerializer,
    UntappdListSubscribeSerializer,
    UntappdRssFeedSerializer,
    UserListCreateSerializer,
    UserListItemCreateSerializer,
    UserListItemSerializer,
    UserListItemUpdateSerializer,
    UserListSerializer,
    UserListUpdateSerializer,
    prime_user_list_context,
)
from beers.models import (
    Beer,
    FollowedList,
    UntappdList,
    UntappdRssFeed,
    UserList,
    UserListItem,
)
from clients.untappd import UntappdClient, UntappdUserNotFound


class UserListViewSet(BrowsableMixin, ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == "create":
            return UserListCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserListUpdateSerializer
        return UserListSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = UserListUpdateSerializer(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            UserListSerializer(instance, context=self.get_serializer_context()).data
        )

    def get_serializer_context(self):
        context = dict(super().get_serializer_context())
        if self.action == "retrieve":
            context["include_items"] = True
        return context

    def get_queryset(self) -> QuerySet[UserList]:
        return (
            UserList.objects.filter(user=self.request.user)
            .select_related("untappd_list")
            .prefetch_related("items")
        )

    def list(self, request, *args, **kwargs):
        owned = list(self.get_queryset())
        followed = self._followed_lists(request.user)

        context = self.get_serializer_context()
        prime_user_list_context(context, owned + followed)

        owned_data = [
            dict(item)
            for item in UserListSerializer(owned, many=True, context=context).data
        ]
        max_sort = max((item["sort_order"] for item in owned_data), default=0)

        followed_data = []
        for i, user_list in enumerate(followed):
            item = dict(UserListSerializer(user_list, context=context).data)
            item["is_followed"] = True
            item["sort_order"] = max_sort + 1 + i
            item["user_name"] = (
                user_list.user.get_full_name() or user_list.user.username
            )
            followed_data.append(item)

        return Response(owned_data + followed_data)

    def _followed_lists(self, user) -> list[UserList]:
        tokens = list(
            FollowedList.objects.filter(user=user).values_list("share_token", flat=True)
        )
        if not tokens:
            return []
        by_token = {
            user_list.share_token: user_list
            for user_list in UserList.objects.filter(share_token__in=tokens)
            .select_related("untappd_list", "user")
            .prefetch_related("items")
        }
        return [by_token[token] for token in tokens if token in by_token]

    def perform_create(self, serializer):
        max_sort = (
            UserList.objects.filter(user=self.request.user).aggregate(
                max_sort=Max("sort_order")
            )["max_sort"]
            or 0
        )
        serializer.save(user=self.request.user, sort_order=max_sort + 1)

    def perform_destroy(self, instance: UserList) -> None:
        untappd_list = instance.untappd_list
        instance.delete()
        if (
            untappd_list
            and not UserList.objects.filter(untappd_list=untappd_list).exists()
        ):
            untappd_list.delete()

    @action(detail=True, methods=["get"], url_path="share")
    def share(self, request, pk=None):
        user_list = self.get_object()
        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="shared/(?P<token>[^/.]+)",
        permission_classes=[permissions.AllowAny],
    )
    def shared(self, request, token: str | None = None):
        user_list = UserList.objects.filter(share_token=token).first()
        if not user_list:
            return Response(status=404)
        serializer = SharedUserListSerializer(user_list)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="shared/(?P<token>[^/.]+)/follow",
        permission_classes=[permissions.IsAuthenticated],
    )
    def follow(self, request, token: str | None = None):
        user_list = UserList.objects.filter(share_token=token).first()
        if not user_list:
            return Response(status=404)
        _, created = FollowedList.objects.get_or_create(
            user=request.user, share_token=token
        )
        return Response(status=201 if created else 200)

    @action(
        detail=False,
        methods=["delete"],
        url_path="shared/(?P<token>[^/.]+)/unfollow",
        permission_classes=[permissions.IsAuthenticated],
    )
    def unfollow(self, request, token: str | None = None):
        deleted, _ = FollowedList.objects.filter(
            user=request.user, share_token=token
        ).delete()
        return Response(status=204 if deleted else 404)

    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        user_list = self.get_object()
        if user_list.is_untappd:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        serializer = UserListItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]
        if not Beer.objects.filter(vmp_id=product_id).exists():
            return Response({"error": "Product not found"}, status=404)
        if UserListItem.objects.filter(list=user_list, product_id=product_id).exists():
            return Response({"error": "Product already in list"}, status=409)
        max_order = user_list.items.aggregate(m=Max("sort_order"))["m"] or 0
        serializer.save(list=user_list, sort_order=max_order + 1)
        return Response(UserListItemSerializer(serializer.instance).data, status=201)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"items/(?P<item_pk>\d+)",
    )
    def item_detail(self, request, pk=None, item_pk: str | None = None):
        user_list = self.get_object()
        if user_list.is_untappd:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        item = user_list.items.filter(pk=item_pk).first()
        if not item:
            return Response(status=404)
        if request.method == "DELETE":
            item.delete()
            return Response(status=204)
        serializer = UserListItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserListItemSerializer(serializer.instance).data)

    @action(
        detail=True,
        methods=["delete"],
        url_path="products/(?P<product_id>[^/.]+)",
    )
    def product_detail(self, request, pk=None, product_id=None):
        user_list = self.get_object()
        if user_list.is_untappd:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        item = user_list.items.filter(product_id=product_id).first()
        if not item:
            return Response(status=404)
        item.delete()
        return Response(status=204)

    @action(detail=False, methods=["post", "patch"], url_path="reorder")
    def reorder_lists(self, request):
        serializer = ListReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        list_ids: list[int] = serializer.validated_data["list_ids"]
        cases = [When(pk=lid, then=Value(i)) for i, lid in enumerate(list_ids)]
        UserList.objects.filter(pk__in=list_ids, user=request.user).update(
            sort_order=Case(*cases, output_field=models.IntegerField())
        )
        return Response(status=204)

    @action(detail=True, methods=["post", "patch"], url_path="items/reorder")
    def reorder_items(self, request, pk=None):
        user_list = self.get_object()
        if user_list.is_untappd:
            return Response(
                {"detail": "Cannot modify items on an Untappd list"}, status=403
            )
        serializer = ItemReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item_ids: list[int] = serializer.validated_data["item_ids"]
        cases = [When(pk=iid, then=Value(i)) for i, iid in enumerate(item_ids)]
        UserListItem.objects.filter(pk__in=item_ids, list=user_list).update(
            sort_order=Case(*cases, output_field=models.IntegerField())
        )
        return Response(status=204)


class UntappdListViewSet(BrowsableMixin, ModelViewSet):
    queryset = UntappdList.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post"]
    lookup_field = "untappd_list_id"

    def list(self, request):
        return Response(status=405)

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        username = request.query_params.get("username", "").strip()
        if not username:
            return Response({"detail": "username parameter is required"}, status=400)

        try:
            lists = UntappdClient.from_options().fetch_user_lists(username)
        except UntappdUserNotFound as e:
            return Response({"detail": str(e)}, status=404)
        except Exception:
            return Response(
                {"detail": "Failed to fetch lists from Untappd"}, status=502
            )

        serializer = UntappdListSearchResultSerializer(lists, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        serializer = UntappdListSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        untappd_list, _created = UntappdList.objects.get_or_create(
            untappd_list_id=data["untappd_list_id"],
            untappd_username=data["untappd_username"],
            defaults={
                "name": data["name"],
                "is_wishlist": data["untappd_list_id"] == 0,
            },
        )

        existing = UserList.objects.filter(
            user=request.user, untappd_list=untappd_list
        ).first()
        if existing:
            return Response(UserListSerializer(existing).data, status=200)

        max_sort = (
            UserList.objects.filter(user=request.user).aggregate(
                max_sort=Max("sort_order")
            )["max_sort"]
            or 0
        )

        user_list = UserList.objects.create(
            user=request.user,
            name=data["name"],
            untappd_list=untappd_list,
            sort_order=max_sort + 1,
        )

        task_id = async_task(
            "beers.tasks.sync_untappd_list_task",
            untappd_list.pk,
        )
        untappd_list.sync_task_id = task_id
        untappd_list.save(update_fields=["sync_task_id"])

        return Response(UserListSerializer(user_list).data, status=201)

    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, untappd_list_id=None):
        user_list = (
            UserList.objects.filter(
                user=request.user, untappd_list__untappd_list_id=untappd_list_id
            )
            .select_related("untappd_list")
            .first()
        )
        if not user_list or not user_list.untappd_list:
            return Response(status=404)

        task_id = async_task(
            "beers.tasks.sync_untappd_list_task",
            user_list.untappd_list.pk,
        )
        user_list.untappd_list.sync_task_id = task_id
        user_list.untappd_list.save(update_fields=["sync_task_id"])

        return Response(UserListSerializer(user_list).data, status=202)


class UntappdRssFeedViewSet(BrowsableMixin, ModelViewSet):
    serializer_class = UntappdRssFeedSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "put", "patch", "delete"]

    def get_queryset(self) -> QuerySet[UntappdRssFeed]:
        return UntappdRssFeed.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        feed = self.get_queryset().first()
        if not feed:
            return Response(status=404)
        return Response(self.get_serializer(feed).data)

    @action(detail=False, methods=["get", "put", "patch", "delete"])
    def me(self, request):
        feed = UntappdRssFeed.objects.filter(user=request.user).first()
        if request.method == "GET":
            if not feed:
                return Response(status=404)
            return Response(self.get_serializer(feed).data)
        if request.method == "DELETE":
            if feed:
                feed.delete()
            return Response(status=204)
        if not feed:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
            return Response(serializer.data, status=201)
        serializer = self.get_serializer(
            feed, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        from beers.tasks import sync_rss_feeds

        feed = UntappdRssFeed.objects.filter(user=request.user, active=True).first()
        if not feed:
            return Response({"error": "No active RSS feed configured"}, status=404)
        try:
            output = sync_rss_feeds(user=request.user.username)
        except Exception:
            return Response({"error": "Sync failed"}, status=500)
        for line in reversed(output.strip().splitlines()):
            try:
                summary = _json.loads(line)
            except (ValueError, TypeError):
                continue
            summary.pop("users_affected", None)
            return Response(summary)
        return Response({"imported": 0, "synced": 0})
