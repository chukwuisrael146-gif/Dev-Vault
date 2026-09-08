from io import BytesIO

from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser


class PayloadTooLarge(APIException):
    status_code = 413
    default_code = "payload_too_large"
    default_detail = "The JSON request exceeds the 64 KiB limit."


class BoundedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        content = stream.read(65537)
        if len(content) > 65536:
            raise PayloadTooLarge()
        try:
            return super().parse(BytesIO(content), media_type, parser_context)
        except (RecursionError, ValueError) as exc:
            raise ParseError("Invalid JSON structure.") from exc
