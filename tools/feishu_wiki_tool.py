"""Feishu Wiki Tool -- create wiki nodes and link documents to the knowledge base.

Provides:
- feishu_wiki_list_spaces     — List all wiki/knowledge base spaces
- feishu_wiki_create_node     — Create a new wiki node (page) under a parent
- feishu_wiki_get_node        — Get node info by token
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


# ---------------------------------------------------------------------------
# feishu_wiki_list_spaces
# ---------------------------------------------------------------------------

_SPACES_URI = "/open-apis/wiki/v2/spaces"

FEISHU_WIKI_LIST_SPACES_SCHEMA = {
    "name": "feishu_wiki_list_spaces",
    "description": "List all wiki/knowledge base spaces available to this tenant. Returns space ID, name, description.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_feishu_wiki_list_spaces(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    try:
        from lark_oapi import AccessTokenType
        from lark_oapi.core.enum import HttpMethod
        from lark_oapi.core.model.base_request import BaseRequest
    except ImportError:
        return tool_error("lark_oapi not installed")

    # First call with default page size
    all_items = []
    page_token = None
    has_more = True

    while has_more:
        query = {"page_size": 50}
        if page_token:
            query["page_token"] = page_token

        request = (
            BaseRequest.builder()
            .http_method(HttpMethod.GET)
            .uri(_SPACES_URI)
            .token_types({AccessTokenType.TENANT})
            .queries(query)
            .build()
        )

        response = client.request(request)

        code = getattr(response, "code", None)
        if code != 0:
            msg = getattr(response, "msg", "unknown error")
            return tool_error(f"Failed to list spaces: code={code} msg={msg}")

        raw = getattr(response, "raw", None)
        if not (raw and hasattr(raw, "content")):
            return tool_error("No response content")

        try:
            body = json.loads(raw.content)
        except (json.JSONDecodeError, AttributeError):
            return tool_error("Failed to parse response")

        data = body.get("data", {}) or {}
        items = data.get("items", [])
        all_items.extend(items)

        page_token = data.get("page_token")
        has_more = data.get("has_more", False)

    # Format the result
    spaces = []
    for item in all_items:
        spaces.append({
            "space_id": item.get("space_id", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "node_creator": getattr(item.get("node_creator"), "obj_type", "") if isinstance(item.get("node_creator"), dict) else "",
        })

    return tool_result(success=True, spaces=spaces)


# ---------------------------------------------------------------------------
# feishu_wiki_create_node
# ---------------------------------------------------------------------------

_CREATE_NODE_URI = "/open-apis/wiki/v2/spaces/:space_id/nodes"

FEISHU_WIKI_CREATE_NODE_SCHEMA = {
    "name": "feishu_wiki_create_node",
    "description": (
        "Create a new wiki page (node) under a parent node in a knowledge base space. "
        "The node can link to an existing document (using obj_token) or be created "
        "as an empty page. Returns the new node's token, URL, and node_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "space_id": {
                "type": "string",
                "description": "The wiki space ID (knowledge base ID). Use feishu_wiki_list_spaces to find it.",
            },
            "title": {
                "type": "string",
                "description": "The page title to display in the knowledge base.",
            },
            "obj_token": {
                "type": "string",
                "description": (
                    "Optional. The token of an existing document (docx) to link to this wiki node. "
                    "When provided, the wiki page becomes a pointer to the document. "
                    "When omitted, a new blank document is created as the wiki page content."
                ),
            },
            "parent_node_token": {
                "type": "string",
                "description": (
                    "Optional. The token of the parent node to create under. "
                    "If omitted, creates a top-level page in the space."
                ),
            },
        },
        "required": ["space_id", "title"],
    },
}


def _handle_feishu_wiki_create_node(args: dict, **kwargs) -> str:
    space_id = args.get("space_id", "").strip()
    title = args.get("title", "").strip()
    obj_token = args.get("obj_token", "").strip() or None
    parent_node_token = args.get("parent_node_token", "").strip() or None

    if not space_id:
        return tool_error("space_id is required")
    if not title:
        return tool_error("title is required")

    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    try:
        from lark_oapi import AccessTokenType
        from lark_oapi.core.enum import HttpMethod
        from lark_oapi.core.model.base_request import BaseRequest
    except ImportError:
        return tool_error("lark_oapi not installed")

    body = {
        "obj_type": "docx",
        "title": title,
        "node_type": "origin",
    }

    if obj_token:
        body["obj_token"] = obj_token
        body["node_type"] = "link"  # link to existing document

    if parent_node_token:
        body["parent_node_token"] = parent_node_token

    uri = _CREATE_NODE_URI.replace(":space_id", space_id)

    request = (
        BaseRequest.builder()
        .http_method(HttpMethod.POST)
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
        .body(json.dumps(body))
        .build()
    )

    response = client.request(request)

    code = getattr(response, "code", None)
    if code != 0:
        msg = getattr(response, "msg", "unknown error")
        return tool_error(f"Failed to create wiki node: code={code} msg={msg}")

    raw = getattr(response, "raw", None)
    if not (raw and hasattr(raw, "content")):
        return tool_error("No response content")

    try:
        body_resp = json.loads(raw.content)
    except (json.JSONDecodeError, AttributeError):
        return tool_error("Failed to parse response")

    data = body_resp.get("data", {}) or {}
    node = data.get("node", {}) or {}

    return tool_result(
        success=True,
        node_token=node.get("node_token", ""),
        node_id=node.get("node_id", ""),
        obj_token=node.get("obj_token", ""),
        title=node.get("title", title),
        space_id=space_id,
        has_child=node.get("has_child", None),
    )


# ---------------------------------------------------------------------------
# feishu_wiki_get_node
# ---------------------------------------------------------------------------

_GET_NODE_URI = "/open-apis/wiki/v2/spaces/get_node"

FEISHU_WIKI_GET_NODE_SCHEMA = {
    "name": "feishu_wiki_get_node",
    "description": "Get wiki node info by node token. Returns the node's title, parent token, has_child status, and document link.",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "The node token to look up.",
            },
        },
        "required": ["token"],
    },
}


def _handle_feishu_wiki_get_node(args: dict, **kwargs) -> str:
    token = args.get("token", "").strip()
    if not token:
        return tool_error("token is required")

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
        .uri(_GET_NODE_URI)
        .token_types({AccessTokenType.TENANT})
        .queries({"token": token})
        .build()
    )

    response = client.request(request)

    code = getattr(response, "code", None)
    if code != 0:
        msg = getattr(response, "msg", "unknown error")
        return tool_error(f"Failed to get node: code={code} msg={msg}")

    raw = getattr(response, "raw", None)
    if not (raw and hasattr(raw, "content")):
        return tool_error("No response content")

    try:
        body = json.loads(raw.content)
    except (json.JSONDecodeError, AttributeError):
        return tool_error("Failed to parse response")

    data = body.get("data", {}) or {}
    node = data.get("node", {}) or {}

    return tool_result(
        success=True,
        node_token=node.get("node_token", ""),
        node_id=node.get("node_id", ""),
        obj_token=node.get("obj_token", ""),
        title=node.get("title", ""),
        has_child=node.get("has_child", False),
        parent_node_token=node.get("parent_node_token", ""),
        space_id=node.get("space_id", ""),
    )


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

def check_requirements() -> bool:
    """Check if Feishu credentials are available."""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return False
    try:
        import lark_oapi  # noqa: F401
        return True
    except ImportError:
        return False


registry.register(
    name="feishu_wiki_list_spaces",
    toolset="feishu_doc",
    schema=FEISHU_WIKI_LIST_SPACES_SCHEMA,
    handler=_handle_feishu_wiki_list_spaces,
    check_fn=check_requirements,
    requires_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
)

registry.register(
    name="feishu_wiki_create_node",
    toolset="feishu_doc",
    schema=FEISHU_WIKI_CREATE_NODE_SCHEMA,
    handler=_handle_feishu_wiki_create_node,
    check_fn=check_requirements,
    requires_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
)

registry.register(
    name="feishu_wiki_get_node",
    toolset="feishu_doc",
    schema=FEISHU_WIKI_GET_NODE_SCHEMA,
    handler=_handle_feishu_wiki_get_node,
    check_fn=check_requirements,
    requires_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
)
