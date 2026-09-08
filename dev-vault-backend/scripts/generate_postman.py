"""Generate a secret-free starter collection; values are filled locally by the developer."""

import json
from pathlib import Path


def request(name, method, path, body=None, *, public=False, verify=False, idempotent=False):
    headers = [{"key": "Content-Type", "value": "application/json"}]
    if not public:
        headers.append(
            {
                "key": "Authorization",
                "value": "Bearer {{api_key}}" if verify else "Bearer {{access_token}}",
            }
        )
    if verify:
        headers.append({"key": "X-DevVault-Service-Token", "value": "{{integration_secret}}"})
    if idempotent:
        headers.append({"key": "Idempotency-Key", "value": "{{operation_id}}"})
    result = {
        "name": name,
        "request": {"method": method, "header": headers, "url": "{{base_url}}/api/v1/" + path},
    }
    if body is not None:
        result["request"]["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    return result


def main():
    items = [
        request(
            "1 Register",
            "POST",
            "auth/register/",
            {
                "email": "{{email}}",
                "password": "{{password}}",
                "password_confirmation": "{{password}}",
            },
            public=True,
        ),
        request(
            "2 Verify email",
            "POST",
            "auth/verify-email/",
            {"token": "{{verification_token}}"},
            public=True,
        ),
        request(
            "3 Login",
            "POST",
            "auth/login/",
            {"email": "{{email}}", "password": "{{password}}"},
            public=True,
        ),
        request("4 Current user", "GET", "me/"),
        request(
            "5 Create organization",
            "POST",
            "organizations/",
            {"name": "My organization", "slug": "my-organization"},
            idempotent=True,
        ),
        request(
            "6 Create project",
            "POST",
            "organizations/{{organization_id}}/projects/",
            {"name": "Orders API", "slug": "orders"},
            idempotent=True,
        ),
        request("7 List environments", "GET", "projects/{{project_id}}/environments/"),
        request(
            "8 Create API service",
            "POST",
            "environments/{{environment_id}}/services/",
            {"name": "Orders", "slug": "orders", "audience": "orders-api"},
            idempotent=True,
        ),
        request(
            "9 Create permission",
            "POST",
            "services/{{service_id}}/permissions/",
            {"name": "orders:read"},
            idempotent=True,
        ),
        request(
            "10 Create rate policy",
            "POST",
            "organizations/{{organization_id}}/policies/",
            {
                "name": "Per-key limit",
                "environment_kind": "test",
                "service_id": "{{service_id}}",
                "algorithm": "fixed_window",
                "dimension": "key",
                "config": {"limit": 60, "window_seconds": 60},
            },
            idempotent=True,
        ),
        request(
            "11 Create quota",
            "POST",
            "organizations/{{organization_id}}/policies/",
            {
                "name": "Daily quota",
                "environment_kind": "test",
                "service_id": "{{service_id}}",
                "algorithm": "daily",
                "dimension": "key",
                "config": {"limit": 1000},
            },
            idempotent=True,
        ),
        request(
            "12 Issue consumer key",
            "POST",
            "environments/{{environment_id}}/keys/",
            {
                "name": "Test consumer",
                "service_id": "{{service_id}}",
                "permission_ids": ["{{permission_id}}"],
            },
            idempotent=True,
        ),
        request(
            "13 Issue server integration credential",
            "POST",
            "services/{{service_id}}/integration-credentials/",
            {"name": "My API backend"},
            idempotent=True,
        ),
        request(
            "14 Verify consumer access",
            "POST",
            "access/verify/",
            {
                "service_id": "{{service_id}}",
                "environment": "test",
                "audience": "orders-api",
                "required_scopes": ["orders:read"],
                "units": 1,
            },
            verify=True,
            idempotent=True,
        ),
        request("15 Usage", "GET", "organizations/{{organization_id}}/usage/"),
        request("16 Audit logs", "GET", "organizations/{{organization_id}}/audit-logs/"),
        request(
            "17 Rotate key",
            "POST",
            "keys/{{key_id}}/rotate/",
            {"confirm": True, "overlap_seconds": 0},
            idempotent=True,
        ),
        request(
            "18 Revoke key",
            "POST",
            "keys/{{key_id}}/revoke/",
            {"confirm": True, "reason": "retired"},
        ),
        request(
            "19 Refresh session",
            "POST",
            "auth/refresh/",
            {"refresh_token": "{{refresh_token}}"},
            public=True,
        ),
        request(
            "20 Logout", "POST", "auth/logout/", {"refresh_token": "{{refresh_token}}"}, public=True
        ),
    ]
    document = {
        "info": {
            "name": "DevVault v1 starter workflow",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": (
                "Use private local variables; never export live tokens. Change operation_id "
                "for each new operation; preserve it only for an exact retry. Copy newly "
                "issued secrets immediately. Full API is in openapi.yaml."
            ),
        },
        "variable": [
            {"key": key, "value": "http://127.0.0.1:8000" if key == "base_url" else ""}
            for key in (
                "base_url",
                "email",
                "password",
                "verification_token",
                "access_token",
                "refresh_token",
                "organization_id",
                "project_id",
                "environment_id",
                "service_id",
                "permission_id",
                "key_id",
                "api_key",
                "integration_secret",
                "operation_id",
            )
        ],
        "item": items,
    }
    path = Path(__file__).resolve().parents[1] / "docs" / "devvault.postman_collection.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print("Generated secret-free Postman starter collection.")


if __name__ == "__main__":
    main()
