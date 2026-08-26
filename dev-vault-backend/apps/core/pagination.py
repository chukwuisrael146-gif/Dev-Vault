from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
