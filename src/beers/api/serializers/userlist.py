from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from django_q.models import OrmQ, Task
from rest_framework import serializers

from beers.models import Beer, Store, UserList, UserListItem


class UserListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = [
            "id",
            "product_id",
            "quantity",
            "year",
            "notes",
            "sort_order",
            "created_at",
        ]
        read_only_fields = ["id", "sort_order", "created_at"]


class UserListItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = ["product_id", "quantity", "year", "notes"]

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1")
        return value


class UserListItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserListItem
        fields = ["quantity", "year", "notes"]

    def validate_quantity(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Quantity must be at least 1")
        return value


def build_price_map(user_lists: Sequence[UserList]) -> dict[str, float]:
    product_ids = {
        item.product_id for user_list in user_lists for item in user_list.items.all()
    }
    if not product_ids:
        return {}
    return {
        str(vmp_id): price
        for vmp_id, price in Beer.objects.filter(vmp_id__in=product_ids).values_list(
            "vmp_id", "price"
        )
    }


def build_untappd_vmp_map(user_lists: Sequence[UserList]) -> dict[int, int]:
    beer_ids = {
        beer_id
        for user_list in user_lists
        if user_list.untappd_list
        for beer_id in user_list.untappd_list.untappd_beer_ids or []
    }
    if not beer_ids:
        return {}
    return dict(
        Beer.objects.filter(untpd_id__in=beer_ids).values_list("untpd_id", "vmp_id")
    )


def build_sync_status_map(user_lists: Sequence[UserList]) -> dict[str, str]:
    task_ids = {
        user_list.untappd_list.sync_task_id
        for user_list in user_lists
        if user_list.untappd_list and user_list.untappd_list.sync_task_id
    }
    if not task_ids:
        return {}
    finished = {
        task_id: "success" if success else "failed"
        for task_id, success in Task.objects.filter(id__in=task_ids).values_list(
            "id", "success"
        )
    }
    queued = set(OrmQ.objects.filter(key__in=task_ids).values_list("key", flat=True))
    return {
        task_id: finished.get(task_id) or ("queued" if task_id in queued else "running")
        for task_id in task_ids
    }


def prime_user_list_context(context: dict, user_lists: Sequence[UserList]) -> None:
    context["price_map"] = build_price_map(user_lists)
    context["untappd_vmp_map"] = build_untappd_vmp_map(user_lists)
    context["sync_status_map"] = build_sync_status_map(user_lists)


class UserListMethodsMixin:
    def _untappd_product_ids(self, obj: UserList) -> list[str] | None:
        if not obj.untappd_list:
            return None
        beer_ids = obj.untappd_list.untappd_beer_ids or []
        if not beer_ids:
            return []
        matched = self.context.get("untappd_vmp_map")
        if matched is None:
            matched = build_untappd_vmp_map([obj])
        seen: set[str] = set()
        result: list[str] = []
        for bid in beer_ids:
            vmp_id = matched.get(bid)
            if vmp_id is None:
                continue
            pid = str(vmp_id)
            if pid in seen:
                continue
            seen.add(pid)
            result.append(pid)
        return result

    def _prices(self, obj: UserList) -> dict[str, float]:
        cached = self.context.get("price_map")
        return cached if cached is not None else build_price_map([obj])

    def get_item_count(self, obj: UserList) -> int:
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return len(untappd_ids)
        return sum(item.quantity for item in obj.items.all())

    def get_product_ids(self, obj: UserList) -> list[str]:
        untappd_ids = self._untappd_product_ids(obj)
        if untappd_ids is not None:
            return untappd_ids
        return [item.product_id for item in obj.items.all()]

    def get_is_past(self, obj: UserList) -> bool | None:
        if not obj.event_date:
            return None
        return obj.event_date < date.today()

    def get_stats(self, obj: UserList) -> dict | None:
        if not obj.show_vintage:
            return None

        items = list(obj.items.all())
        if not items:
            return {
                "total_bottles": 0,
                "total_value": 0,
                "oldest_year": None,
                "newest_year": None,
            }

        years = [item.year for item in items if item.year is not None]
        prices = self._prices(obj)

        return {
            "total_bottles": sum(item.quantity for item in items),
            "total_value": round(
                sum(
                    item.quantity * (prices.get(item.product_id) or 0) for item in items
                ),
                2,
            ),
            "oldest_year": min(years) if years else None,
            "newest_year": max(years) if years else None,
        }

    def get_total_price(self, obj: UserList) -> float | None:
        if not obj.show_store:
            return None

        prices = self._prices(obj)
        return round(
            sum(
                item.quantity * (prices.get(item.product_id) or 0)
                for item in obj.items.all()
            ),
            2,
        )

    def get_is_read_only(self, obj: UserList) -> bool:
        return obj.is_untappd


class UserListSerializer(UserListMethodsMixin, serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    product_ids = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    untappd_list_id = serializers.IntegerField(
        source="untappd_list.untappd_list_id", read_only=True, default=None
    )
    untappd_username = serializers.CharField(
        source="untappd_list.untappd_username", read_only=True, default=None
    )
    is_read_only = serializers.SerializerMethodField()
    last_synced = serializers.DateTimeField(
        source="untappd_list.last_synced", read_only=True, default=None
    )
    sync_status = serializers.SerializerMethodField()

    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "selected_store_id",
            "event_date",
            "show_quantity",
            "show_store",
            "show_vintage",
            "show_prices",
            "show_notes",
            "share_token",
            "sort_order",
            "created_at",
            "updated_at",
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
            "sync_status",
        ]
        read_only_fields = [
            "id",
            "share_token",
            "created_at",
            "updated_at",
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
            "sync_status",
        ]

    def get_sync_status(self, obj: UserList) -> str | None:
        if not obj.untappd_list:
            return None
        task_id = obj.untappd_list.sync_task_id
        if not task_id:
            return None
        statuses = self.context.get("sync_status_map")
        if statuses is None:
            statuses = build_sync_status_map([obj])
        return statuses.get(task_id)

    def get_items(self, obj: UserList):
        if not self.context.get("include_items", False):
            return None
        items = obj.items.all()
        return UserListItemSerializer(
            items, many=True, context={"selected_store_id": obj.selected_store_id}
        ).data

    def to_representation(self, instance: UserList):
        data = super().to_representation(instance)
        if data.get("is_past") is None:
            data.pop("is_past", None)
        if not instance.show_vintage:
            data.pop("stats", None)
        if data.get("items") is None:
            data.pop("items", None)
        if not instance.show_store:
            data.pop("total_price", None)
        if instance.untappd_list_id is None:
            data.pop("untappd_list_id", None)
            data.pop("untappd_username", None)
            data.pop("last_synced", None)
        return data


FLAG_KEYS = frozenset(
    {"show_quantity", "show_store", "show_vintage", "show_prices", "show_notes"}
)

FLAG_DEFAULTS: dict[str, dict[str, bool]] = {
    "shopping": {"show_quantity": True, "show_store": True},
    "cellar": {"show_quantity": True, "show_vintage": True},
}


def apply_flag_defaults(validated_data: dict, list_type: str | None) -> None:
    if not list_type or any(key in validated_data for key in FLAG_KEYS):
        return
    validated_data.update(FLAG_DEFAULTS.get(list_type, {}))


class UserListCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "event_date",
            "show_quantity",
            "show_store",
            "show_vintage",
            "show_prices",
            "show_notes",
            "sort_order",
            "share_token",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sort_order",
            "share_token",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data: dict) -> UserList:
        apply_flag_defaults(validated_data, validated_data.pop("list_type", None))
        return super().create(validated_data)


class UserListUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserList
        fields = [
            "name",
            "description",
            "selected_store_id",
            "event_date",
            "list_type",
            "show_quantity",
            "show_store",
            "show_vintage",
            "show_prices",
            "show_notes",
        ]

    def update(self, instance: UserList, validated_data: dict) -> UserList:
        apply_flag_defaults(validated_data, validated_data.pop("list_type", None))
        return super().update(instance, validated_data)


class SharedUserListSerializer(UserListMethodsMixin, serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()
    product_ids = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    untappd_list_id = serializers.IntegerField(
        source="untappd_list.untappd_list_id", read_only=True, default=None
    )
    untappd_username = serializers.CharField(
        source="untappd_list.untappd_username", read_only=True, default=None
    )
    is_read_only = serializers.SerializerMethodField()
    last_synced = serializers.DateTimeField(
        source="untappd_list.last_synced", read_only=True, default=None
    )

    class Meta:
        model = UserList
        fields = [
            "id",
            "name",
            "description",
            "list_type",
            "selected_store_id",
            "store_name",
            "event_date",
            "show_quantity",
            "show_store",
            "show_vintage",
            "show_prices",
            "show_notes",
            "share_token",
            "sort_order",
            "created_at",
            "updated_at",
            "user_name",
            "item_count",
            "product_ids",
            "is_past",
            "stats",
            "items",
            "total_price",
            "untappd_list_id",
            "untappd_username",
            "is_read_only",
            "last_synced",
        ]

    def get_items(self, obj: UserList):
        items = obj.items.all()
        return UserListItemSerializer(
            items, many=True, context={"selected_store_id": obj.selected_store_id}
        ).data

    def get_user_name(self, obj: UserList) -> str:
        if obj.user.first_name or obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.username

    def get_store_name(self, obj: UserList) -> str | None:
        if obj.selected_store_id:
            return getattr(obj, "_store_name", None) or (
                Store.objects.filter(store_id=obj.selected_store_id)
                .values_list("name", flat=True)
                .first()
            )
        return None

    def to_representation(self, instance: UserList):
        data = super().to_representation(instance)
        if data.get("is_past") is None:
            data.pop("is_past", None)
        if not instance.show_vintage:
            data.pop("stats", None)
        if not instance.show_store:
            data.pop("total_price", None)
        if instance.untappd_list_id is None:
            data.pop("untappd_list_id", None)
            data.pop("untappd_username", None)
            data.pop("last_synced", None)
        return data


class UntappdListSearchResultSerializer(serializers.Serializer):
    list_id = serializers.IntegerField()
    name = serializers.CharField()
    item_count = serializers.IntegerField()


class UntappdListSubscribeSerializer(serializers.Serializer):
    untappd_list_id = serializers.IntegerField()
    untappd_username = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)


class ListReorderSerializer(serializers.Serializer):
    list_ids = serializers.ListField(child=serializers.IntegerField())


class ItemReorderSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField())
