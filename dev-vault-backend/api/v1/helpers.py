from rest_framework import serializers

from apps.core.pagination import DefaultCursorPagination


class StrictInput(serializers.Serializer):
    """Reject unsupported mutation fields rather than silently accepting them."""

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["The request contains unsupported fields."]}
            )
        return super().to_internal_value(data)


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def paginated(queryset, serializer_class, request):
    paginator = DefaultCursorPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)
