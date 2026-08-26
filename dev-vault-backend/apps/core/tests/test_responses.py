from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apps.core.responses import api_exception_handler


def test_validation_error_uses_stable_envelope() -> None:
    request = APIRequestFactory().post("/example/", {}, format="json")
    request.correlation_id = "request-456"

    response = api_exception_handler(
        ValidationError({"name": ["This field is required."]}),
        {"request": request, "view": None},
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["request_id"] == "request-456"
    assert "name" in response.data["error"]["details"]
