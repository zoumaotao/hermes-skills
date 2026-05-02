"""Feishu Document & Drive Tools -- read, create, upload, import documents.

Provides:
- feishu_doc_read         — Read document content as plain text
- feishu_doc_create       — Create a new blank document
- feishu_doc_add_blocks   — Add content blocks to a document
- feishu_drive_upload     — Upload a file to Feishu Drive (云盘)
- feishu_drive_import     — Import an uploaded file as a Feishu doc (云文档)
"""

import json
import logging
import os
import threading
from typing import Any, Optional

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# Thread-local storage for the lark client.
_local = threading.local()


def set_client(client):
    """Store a lark client for the current thread."""
    _local.client = client


def get_client():
    """Return the lark client.

    Uses thread-local injected client first, otherwise creates one from
    environment variables (FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DOMAIN).
    """
    client = getattr(_local, "client", None)
    if client is not None:
        return client

    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return None

    try:
        import lark_oapi as lark
    except ImportError:
        return None

    domain_name = os.environ.get("FEISHU_DOMAIN", "feishu").strip().lower()
    from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

    domain = FEISHU_DOMAIN if domain_name != "lark" else LARK_DOMAIN

    client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .domain(domain)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )
    _local.client = client
    return client


def _do_request(client, method, uri, paths=None, queries=None, body=None):
    """Build and execute a BaseRequest, return (code, msg, data_dict)."""
    from lark_oapi import AccessTokenType
    from lark_oapi.core.enum import HttpMethod
    from lark_oapi.core.model.base_request import BaseRequest

    http_method = HttpMethod.GET if method == "GET" else HttpMethod.POST

    builder = (
        BaseRequest.builder()
        .http_method(http_method)
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
    )
    if paths:
        builder = builder.paths(paths)
    if queries:
        builder = builder.queries(queries)
    if body is not None:
        builder = builder.body(body)

    request = builder.build()
    response = client.request(request)

    code = getattr(response, "code", None)
    msg = getattr(response, "msg", "")

    data = {}
    raw = getattr(response, "raw", None)
    if raw and hasattr(raw, "content"):
        try:
            body_json = json.loads(raw.content)
            data = body_json.get("data", {})
        except (json.JSONDecodeError, AttributeError):
            pass
    if not data:
        resp_data = getattr(response, "data", None)
        if isinstance(resp_data, dict):
            data = resp_data
        elif resp_data and hasattr(resp_data, "__dict__"):
            data = vars(resp_data)

    return code, msg, data


def _check_feishu():
    try:
        import lark_oapi  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Helper: get root folder token
# ---------------------------------------------------------------------------

def _get_root_folder_token(client) -> Optional[str]:
    """Get the root folder token of the Feishu Drive."""
    code, msg, data = _do_request(client, "GET", "/open-apis/drive/explorer/v2/root_folder/meta")
    if code == 0:
        return data.get("token", "")
    logger.warning("[Feishu] Failed to get root folder: code=%s msg=%s", code, msg)
    return None


# ---------------------------------------------------------------------------
# feishu_doc_read
# ---------------------------------------------------------------------------

_RAW_CONTENT_URI = "/open-apis/docx/v1/documents/:document_id/raw_content"

FEISHU_DOC_READ_SCHEMA = {
    "name": "feishu_doc_read",
    "description": (
        "Read the full content of a Feishu/Lark document as plain text. "
        "Useful when you need more context beyond the quoted text in a comment."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc_token": {
                "type": "string",
                "description": "The document token (from the document URL or comment context).",
            },
        },
        "required": ["doc_token"],
    },
}


def _handle_feishu_doc_read(args: dict, **kwargs) -> str:
    doc_token = args.get("doc_token", "").strip()
    if not doc_token:
        return tool_error("doc_token is required")

    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    try:
        from lark_oapi import AccessTokenType
        from lark_oapi.core.enum import HttpMethod
        from lark_oapi.core.model.base_request import BaseRequest
    except ImportError:
        return tool_error("lark_oapi not installed")

    request = (
        BaseRequest.builder()
        .http_method(HttpMethod.GET)
        .uri(_RAW_CONTENT_URI)
        .token_types({AccessTokenType.TENANT})
        .paths({"document_id": doc_token})
        .build()
    )

    response = client.request(request)

    code = getattr(response, "code", None)
    if code != 0:
        msg = getattr(response, "msg", "unknown error")
        return tool_error(f"Failed to read document: code={code} msg={msg}")

    raw = getattr(response, "raw", None)
    if raw and hasattr(raw, "content"):
        try:
            body = json.loads(raw.content)
            content = body.get("data", {}).get("content", "")
            return tool_result(success=True, content=content)
        except (json.JSONDecodeError, AttributeError):
            pass

    data = getattr(response, "data", None)
    if data:
        if isinstance(data, dict):
            content = data.get("content", "")
        else:
            content = getattr(data, "content", str(data))
        return tool_result(success=True, content=content)

    return tool_error("No content returned from document API")


# ---------------------------------------------------------------------------
# feishu_doc_create
# ---------------------------------------------------------------------------

FEISHU_DOC_CREATE_SCHEMA = {
    "name": "feishu_doc_create",
    "description": (
        "Create a new Feishu document (docx). "
        "Returns the document token and URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The document title.",
            },
        },
        "required": ["title"],
    },
}


def _handle_feishu_doc_create(args: dict, **kwargs) -> str:
    title = args.get("title", "").strip()
    if not title:
        return tool_error("title is required")

    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    code, msg, data = _do_request(
        client, "POST", "/open-apis/docx/v1/documents",
        body={"title": title},
    )
    if code != 0:
        return tool_error(f"Create document failed: code={code} msg={msg}")

    doc_token = data.get("document", {}).get("document_id", "")
    url = f"https://bytedance.feishu.cn/docx/{doc_token}" if doc_token else ""
    return tool_result({
        "document_token": doc_token,
        "url": url,
    })


# ---------------------------------------------------------------------------
# feishu_drive_upload
# ---------------------------------------------------------------------------

FEISHU_DRIVE_UPLOAD_SCHEMA = {
    "name": "feishu_drive_upload",
    "description": (
        "Upload a file to the Feishu/Lark Drive (云盘). "
        "Supports any file type. "
        "Returns the file_token that can be used for feishu_drive_import."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the local file to upload.",
            },
            "file_name": {
                "type": "string",
                "description": "Filename to use in Drive (optional, defaults to original filename).",
            },
        },
        "required": ["file_path"],
    },
}


def _handle_feishu_drive_upload(args: dict, **kwargs) -> str:
    import os as _os

    file_path = args.get("file_path", "").strip()
    if not file_path:
        return tool_error("file_path is required")

    file_path = _os.path.expanduser(file_path)
    if not _os.path.isfile(file_path):
        return tool_error(f"File not found: {file_path}")

    file_name = args.get("file_name", "").strip() or _os.path.basename(file_path)
    file_size = _os.path.getsize(file_path)

    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    root_token = _get_root_folder_token(client)
    if not root_token:
        return tool_error("Failed to get root folder token")

    # Determine mime type
    ext = _os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".md": "text/markdown",
        ".html": "text/html",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".js": "application/javascript",
        ".ts": "application/typescript",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    content_type = mime_map.get(ext, "application/octet-stream")

    # Use raw requests to upload via multipart
    import requests

    # Get tenant access token
    base = "https://open.feishu.cn"
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()

    token_resp = requests.post(
        f"{base}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    token_data = token_resp.json()
    access_token = token_data.get("tenant_access_token", "")
    if not access_token:
        return tool_error("Failed to get tenant access token")

    with open(file_path, "rb") as f:
        files_payload = {
            "file_name": (None, file_name),
            "parent_type": (None, "explorer"),
            "parent_node": (None, root_token),
            "size": (None, str(file_size)),
            "file": (file_name, f, content_type),
        }
        upload_resp = requests.post(
            f"{base}/open-apis/drive/v1/files/upload_all",
            headers={"Authorization": f"Bearer {access_token}"},
            files=files_payload,
            timeout=60,
        )

    try:
        result = upload_resp.json()
    except Exception:
        return tool_error(f"Upload failed: {upload_resp.status_code} {upload_resp.text[:300]}")

    if result.get("code") != 0:
        return tool_error(f"Upload failed: code={result.get('code')} msg={result.get('msg')}")

    file_token = result.get("data", {}).get("file_token", "")
    return tool_result({
        "file_token": file_token,
        "file_name": file_name,
        "url": f"https://bytedance.feishu.cn/file/{file_token}" if file_token else "",
    })


# ---------------------------------------------------------------------------
# feishu_drive_import
# ---------------------------------------------------------------------------

FEISHU_DRIVE_IMPORT_SCHEMA = {
    "name": "feishu_drive_import",
    "description": (
        "Import an uploaded file as a Feishu document (docx). "
        "Takes a file_token from feishu_drive_upload and converts it into a "
        "native Feishu doc. Supports Markdown (.md) and HTML (.html) files. "
        "Returns the document token and URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_token": {
                "type": "string",
                "description": "The file_token returned by feishu_drive_upload.",
            },
            "file_name": {
                "type": "string",
                "description": "The document title to use in Feishu.",
            },
            "file_extension": {
                "type": "string",
                "description": "The file extension (e.g. 'md', 'html'). Default: 'md'.",
            },
        },
        "required": ["file_token", "file_name"],
    },
}


def _handle_feishu_drive_import(args: dict, **kwargs) -> str:
    import time
    import requests

    file_token = args.get("file_token", "").strip()
    file_name = args.get("file_name", "").strip()
    file_extension = args.get("file_extension", "md").strip().lower()

    if not file_token or not file_name:
        return tool_error("file_token and file_name are required")

    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    root_token = _get_root_folder_token(client)
    if not root_token:
        return tool_error("Failed to get root folder token")

    # Get tenant access token
    base = "https://open.feishu.cn"
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()

    token_resp = requests.post(
        f"{base}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    access_token = token_resp.json().get("tenant_access_token", "")
    if not access_token:
        return tool_error("Failed to get tenant access token")

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Create import task
    import_body = {
        "type": "docx",
        "file_name": file_name,
        "file_extension": file_extension,
        "file_token": file_token,
        "point": {
            "mount_type": 1,
            "mount_key": root_token,
        },
    }

    import_resp = requests.post(
        f"{base}/open-apis/drive/v1/import_tasks",
        headers=headers,
        json=import_body,
        timeout=30,
    )

    try:
        import_result = import_resp.json()
    except Exception:
        return tool_error(f"Import task failed: {import_resp.status_code} {import_resp.text[:300]}")

    if import_result.get("code") != 0:
        return tool_error(
            f"Import task failed: code={import_result.get('code')} "
            f"msg={import_result.get('msg')}"
        )

    ticket = import_result.get("data", {}).get("ticket", "")
    if not ticket:
        return tool_error("Import task created but no ticket returned")

    # Poll for result
    for _ in range(10):
        time.sleep(2)
        poll_resp = requests.get(
            f"{base}/open-apis/drive/v1/import_tasks/{ticket}",
            headers=headers,
            timeout=15,
        )
        try:
            poll_data = poll_resp.json()
        except Exception:
            continue

        if poll_data.get("code") != 0:
            continue

        result = poll_data.get("data", {}).get("result", {})
        job_status = result.get("job_status", -1)
        if job_status == 0:  # completed
            doc_token = result.get("token", "")
            doc_url = result.get("url", "")
            return tool_result({
                "document_token": doc_token,
                "url": doc_url,
                "ticket": ticket,
            })
        elif job_status == 1:  # failed
            error_msg = result.get("job_error_msg", "unknown")
            return tool_error(f"Import failed: {error_msg}")

    return tool_error("Import timed out after ~20s")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(
    name="feishu_doc_read",
    toolset="feishu_doc",
    schema=FEISHU_DOC_READ_SCHEMA,
    handler=_handle_feishu_doc_read,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Read Feishu document content",
    emoji="\U0001f4c4",
)

registry.register(
    name="feishu_doc_create",
    toolset="feishu_doc",
    schema=FEISHU_DOC_CREATE_SCHEMA,
    handler=_handle_feishu_doc_create,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Create a Feishu document",
    emoji="\U0001f4c4",
)

registry.register(
    name="feishu_drive_upload",
    toolset="feishu_doc",
    schema=FEISHU_DRIVE_UPLOAD_SCHEMA,
    handler=_handle_feishu_drive_upload,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Upload a file to Feishu Drive",
    emoji="\U0001f4c1",
)

registry.register(
    name="feishu_drive_import",
    toolset="feishu_doc",
    schema=FEISHU_DRIVE_IMPORT_SCHEMA,
    handler=_handle_feishu_drive_import,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Import a file as a Feishu document",
    emoji="\U0001f4c4",
)

