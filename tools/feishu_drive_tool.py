"""Feishu Drive Tools -- document comment operations via Feishu/Lark API.

Provides tools for listing, replying to, and adding document comments.
Uses the same lazy-import + BaseRequest pattern as feishu_comment.py.
The lark client is injected per-thread by the comment event handler.
"""

import json
import logging
import os
import threading

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# Thread-local storage for the lark client injected by feishu_comment handler.
_local = threading.local()


def set_client(client):
    """Store a lark client for the current thread (called by feishu_comment)."""
    _local.client = client


def get_client():
    """Return the lark client for the current thread.

    If a client has been injected by feishu_comment handler, returns that.
    Otherwise, creates a new client from environment variables
    (FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DOMAIN).
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


def _check_feishu():
    try:
        import lark_oapi  # noqa: F401
        return True
    except ImportError:
        return False


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

    # Tool handlers run synchronously in a worker thread (no running event
    # loop), so call the blocking lark client directly.
    response = client.request(request)

    code = getattr(response, "code", None)
    msg = getattr(response, "msg", "")

    # Parse response data
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


# ---------------------------------------------------------------------------
# feishu_drive_list_comments
# ---------------------------------------------------------------------------

_LIST_COMMENTS_URI = "/open-apis/drive/v1/files/:file_token/comments"

FEISHU_DRIVE_LIST_COMMENTS_SCHEMA = {
    "name": "feishu_drive_list_comments",
    "description": (
        "List comments on a Feishu document. "
        "Use is_whole=true to list whole-document comments only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_token": {
                "type": "string",
                "description": "The document file token.",
            },
            "file_type": {
                "type": "string",
                "description": "File type (default: docx).",
                "default": "docx",
            },
            "is_whole": {
                "type": "boolean",
                "description": "If true, only return whole-document comments.",
                "default": False,
            },
            "page_size": {
                "type": "integer",
                "description": "Number of comments per page (max 100).",
                "default": 100,
            },
            "page_token": {
                "type": "string",
                "description": "Pagination token for next page.",
            },
        },
        "required": ["file_token"],
    },
}


def _handle_list_comments(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    file_token = args.get("file_token", "").strip()
    if not file_token:
        return tool_error("file_token is required")

    file_type = args.get("file_type", "docx") or "docx"
    is_whole = args.get("is_whole", False)
    page_size = args.get("page_size", 100)
    page_token = args.get("page_token", "")

    queries = [
        ("file_type", file_type),
        ("user_id_type", "open_id"),
        ("page_size", str(page_size)),
    ]
    if is_whole:
        queries.append(("is_whole", "true"))
    if page_token:
        queries.append(("page_token", page_token))

    code, msg, data = _do_request(
        client, "GET", _LIST_COMMENTS_URI,
        paths={"file_token": file_token},
        queries=queries,
    )
    if code != 0:
        return tool_error(f"List comments failed: code={code} msg={msg}")

    return tool_result(data)


# ---------------------------------------------------------------------------
# feishu_drive_list_comment_replies
# ---------------------------------------------------------------------------

_LIST_REPLIES_URI = "/open-apis/drive/v1/files/:file_token/comments/:comment_id/replies"

FEISHU_DRIVE_LIST_REPLIES_SCHEMA = {
    "name": "feishu_drive_list_comment_replies",
    "description": "List all replies in a comment thread on a Feishu document.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_token": {
                "type": "string",
                "description": "The document file token.",
            },
            "comment_id": {
                "type": "string",
                "description": "The comment ID to list replies for.",
            },
            "file_type": {
                "type": "string",
                "description": "File type (default: docx).",
                "default": "docx",
            },
            "page_size": {
                "type": "integer",
                "description": "Number of replies per page (max 100).",
                "default": 100,
            },
            "page_token": {
                "type": "string",
                "description": "Pagination token for next page.",
            },
        },
        "required": ["file_token", "comment_id"],
    },
}


def _handle_list_replies(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    file_token = args.get("file_token", "").strip()
    comment_id = args.get("comment_id", "").strip()
    if not file_token or not comment_id:
        return tool_error("file_token and comment_id are required")

    file_type = args.get("file_type", "docx") or "docx"
    page_size = args.get("page_size", 100)
    page_token = args.get("page_token", "")

    queries = [
        ("file_type", file_type),
        ("user_id_type", "open_id"),
        ("page_size", str(page_size)),
    ]
    if page_token:
        queries.append(("page_token", page_token))

    code, msg, data = _do_request(
        client, "GET", _LIST_REPLIES_URI,
        paths={"file_token": file_token, "comment_id": comment_id},
        queries=queries,
    )
    if code != 0:
        return tool_error(f"List replies failed: code={code} msg={msg}")

    return tool_result(data)


# ---------------------------------------------------------------------------
# feishu_drive_reply_comment
# ---------------------------------------------------------------------------

_REPLY_COMMENT_URI = "/open-apis/drive/v1/files/:file_token/comments/:comment_id/replies"

FEISHU_DRIVE_REPLY_SCHEMA = {
    "name": "feishu_drive_reply_comment",
    "description": (
        "Reply to a local comment thread on a Feishu document. "
        "Use this for local (quoted-text) comments. "
        "For whole-document comments, use feishu_drive_add_comment instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_token": {
                "type": "string",
                "description": "The document file token.",
            },
            "comment_id": {
                "type": "string",
                "description": "The comment ID to reply to.",
            },
            "content": {
                "type": "string",
                "description": "The reply text content (plain text only, no markdown).",
            },
            "file_type": {
                "type": "string",
                "description": "File type (default: docx).",
                "default": "docx",
            },
        },
        "required": ["file_token", "comment_id", "content"],
    },
}


def _handle_reply_comment(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    file_token = args.get("file_token", "").strip()
    comment_id = args.get("comment_id", "").strip()
    content = args.get("content", "").strip()
    if not file_token or not comment_id or not content:
        return tool_error("file_token, comment_id, and content are required")

    file_type = args.get("file_type", "docx") or "docx"

    body = {
        "content": {
            "elements": [
                {
                    "type": "text_run",
                    "text_run": {"text": content},
                }
            ]
        }
    }

    code, msg, data = _do_request(
        client, "POST", _REPLY_COMMENT_URI,
        paths={"file_token": file_token, "comment_id": comment_id},
        queries=[("file_type", file_type)],
        body=body,
    )
    if code != 0:
        return tool_error(f"Reply comment failed: code={code} msg={msg}")

    return tool_result(success=True, data=data)


# ---------------------------------------------------------------------------
# feishu_drive_add_comment
# ---------------------------------------------------------------------------

_ADD_COMMENT_URI = "/open-apis/drive/v1/files/:file_token/new_comments"

FEISHU_DRIVE_ADD_COMMENT_SCHEMA = {
    "name": "feishu_drive_add_comment",
    "description": (
        "Add a new whole-document comment on a Feishu document. "
        "Use this for whole-document comments or as a fallback when "
        "reply_comment fails with code 1069302."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_token": {
                "type": "string",
                "description": "The document file token.",
            },
            "content": {
                "type": "string",
                "description": "The comment text content (plain text only, no markdown).",
            },
            "file_type": {
                "type": "string",
                "description": "File type (default: docx).",
                "default": "docx",
            },
        },
        "required": ["file_token", "content"],
    },
}


def _handle_add_comment(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    file_token = args.get("file_token", "").strip()
    content = args.get("content", "").strip()
    if not file_token or not content:
        return tool_error("file_token and content are required")

    file_type = args.get("file_type", "docx") or "docx"

    body = {
        "file_type": file_type,
        "reply_elements": [
            {"type": "text", "text": content},
        ],
    }

    code, msg, data = _do_request(
        client, "POST", _ADD_COMMENT_URI,
        paths={"file_token": file_token},
        body=body,
    )
    if code != 0:
        return tool_error(f"Add comment failed: code={code} msg={msg}")

    return tool_result(success=True, data=data)


# ---------------------------------------------------------------------------
# feishu_doc_create
# ---------------------------------------------------------------------------

_CREATE_DOC_URI = "/open-apis/docx/v1/documents"

FEISHU_DOC_CREATE_SCHEMA = {
    "name": "feishu_doc_create",
    "description": (
        "Create a new Feishu document (docx). "
        "Returns the document token and URL. "
        "Use this to create documents programmatically."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The document title.",
            },
            "folder_token": {
                "type": "string",
                "description": "Optional folder token to place the document in.",
            },
        },
        "required": ["title"],
    },
}


def _handle_create_doc(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    title = args.get("title", "").strip()
    if not title:
        return tool_error("title is required")

    body = {"title": title}
    folder_token = args.get("folder_token", "").strip()
    if folder_token:
        body["folder_token"] = folder_token

    code, msg, data = _do_request(
        client, "POST", _CREATE_DOC_URI,
        body=body,
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
# feishu_doc_add_blocks
# ---------------------------------------------------------------------------

_ADD_BLOCKS_URI = "/open-apis/docx/v1/documents/:document_id/blocks/:block_id/children"

FEISHU_DOC_ADD_BLOCKS_SCHEMA = {
    "name": "feishu_doc_add_blocks",
    "description": (
        "Add content blocks to a Feishu document. "
        "Use after feishu_doc_create to populate the document with content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The document ID (document_token from feishu_doc_create).",
            },
            "blocks": {
                "type": "string",
                "description": (
                    "JSON array of block objects. Types: 1=text, 2=heading1..10=heading9, "
                    "11=bullet, 12=ordered, 13=code, 14=quote, 22=divider. "
                    "Each block needs 'block_type' and a type-specific key (e.g. heading2, text, code)."
                ),
            },
        },
        "required": ["document_id", "blocks"],
    },
}


def _handle_add_blocks(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available (not in a Feishu comment context)")

    document_id = args.get("document_id", "").strip()
    blocks_json = args.get("blocks", "").strip()
    if not document_id or not blocks_json:
        return tool_error("document_id and blocks are required")

    try:
        blocks = json.loads(blocks_json)
    except json.JSONDecodeError as e:
        return tool_error(f"blocks is not valid JSON: {e}")

    body = {"children": blocks}

    code, msg, data = _do_request(
        client, "POST", _ADD_BLOCKS_URI,
        paths={"document_id": document_id, "block_id": document_id},
        body=body,
    )
    if code != 0:
        return tool_error(f"Add blocks failed: code={code} msg={msg}")

    return tool_result(data)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(
    name="feishu_drive_list_comments",
    toolset="feishu_drive",
    schema=FEISHU_DRIVE_LIST_COMMENTS_SCHEMA,
    handler=_handle_list_comments,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="List document comments",
    emoji="\U0001f4ac",
)

registry.register(
    name="feishu_drive_list_comment_replies",
    toolset="feishu_drive",
    schema=FEISHU_DRIVE_LIST_REPLIES_SCHEMA,
    handler=_handle_list_replies,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="List comment replies",
    emoji="\U0001f4ac",
)

registry.register(
    name="feishu_drive_reply_comment",
    toolset="feishu_drive",
    schema=FEISHU_DRIVE_REPLY_SCHEMA,
    handler=_handle_reply_comment,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Reply to a document comment",
    emoji="\u2709\ufe0f",
)

registry.register(
    name="feishu_drive_add_comment",
    toolset="feishu_drive",
    schema=FEISHU_DRIVE_ADD_COMMENT_SCHEMA,
    handler=_handle_add_comment,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Add a whole-document comment",
    emoji="\u2709\ufe0f",
)

registry.register(
    name="feishu_doc_create",
    toolset="feishu_drive",
    schema=FEISHU_DOC_CREATE_SCHEMA,
    handler=_handle_create_doc,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Create a Feishu document",
    emoji="\U0001f4c4",
)

registry.register(
    name="feishu_doc_add_blocks",
    toolset="feishu_drive",
    schema=FEISHU_DOC_ADD_BLOCKS_SCHEMA,
    handler=_handle_add_blocks,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Add content blocks to a Feishu document",
    emoji="\U0001f4dd",
)

# ---------------------------------------------------------------------------
# feishu_wiki_list_spaces
# ---------------------------------------------------------------------------

_WIKI_LIST_SPACES_URI = "/open-apis/wiki/v2/spaces"

FEISHU_WIKI_LIST_SPACES_SCHEMA = {
    "name": "feishu_wiki_list_spaces",
    "description": (
        "List all Feishu wiki/knowledge-base spaces accessible to the bot. "
        "Returns space_id, name, description for each space."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_wiki_list_spaces(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    code, msg, data = _do_request(client, "GET", _WIKI_LIST_SPACES_URI)
    if code != 0:
        return tool_error(f"List wiki spaces failed: code={code} msg={msg}")

    items = data.get("items", [])
    spaces = [
        {
            "space_id": s.get("space_id", ""),
            "name": s.get("name", ""),
            "description": s.get("description", ""),
        }
        for s in items
    ]
    return tool_result({"spaces": spaces})


# ---------------------------------------------------------------------------
# feishu_wiki_create_node
# ---------------------------------------------------------------------------

_WIKI_CREATE_NODE_URI = "/open-apis/wiki/v2/spaces/:space_id/nodes"

FEISHU_WIKI_CREATE_NODE_SCHEMA = {
    "name": "feishu_wiki_create_node",
    "description": (
        "Create a node (document entry) in a Feishu wiki/knowledge-base space. "
        "Use after feishu_doc_create to link the document into a wiki space. "
        "Returns the node_token and URL of the created node."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "space_id": {
                "type": "string",
                "description": "The wiki space ID (from feishu_wiki_list_spaces).",
            },
            "node_type": {
                "type": "string",
                "description": "Node type: 'origin' (create new blank doc), 'link' (link existing doc). Default: 'origin'",
                "default": "origin",
            },
            "obj_token": {
                "type": "string",
                "description": (
                    "Required when node_type='link'. The document token from "
                    "feishu_doc_create to link into the wiki space."
                ),
            },
            "title": {
                "type": "string",
                "description": "The title of the wiki page.",
            },
            "parent_node_token": {
                "type": "string",
                "description": "Optional parent node token to place under a specific folder in the wiki.",
            },
        },
        "required": ["space_id", "title"],
    },
}


def _handle_wiki_create_node(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    space_id = args.get("space_id", "").strip()
    title = args.get("title", "").strip()
    if not space_id or not title:
        return tool_error("space_id and title are required")

    node_type = args.get("node_type", "origin").strip()
    obj_token = args.get("obj_token", "").strip()
    parent_node_token = args.get("parent_node_token", "").strip()

    body = {
        "obj_type": "page",
        "node_type": node_type,
        "title": title,
    }
    if node_type == "link" and obj_token:
        body["obj_token"] = obj_token
    if parent_node_token:
        body["parent_node_token"] = parent_node_token

    code, msg, data = _do_request(
        client, "POST", _WIKI_CREATE_NODE_URI,
        paths={"space_id": space_id},
        body=body,
    )
    if code != 0:
        return tool_error(f"Create wiki node failed: code={code} msg={msg}")

    node = data.get("node", {})
    node_token = node.get("node_token", "")
    obj_token_out = node.get("obj_token", "")
    url = f"https://bytedance.feishu.cn/wiki/{node_token}" if node_token else ""
    return tool_result({
        "node_token": node_token,
        "obj_token": obj_token_out,
        "url": url,
        "space_id": space_id,
        "title": node.get("title", title),
    })


registry.register(
    name="feishu_wiki_list_spaces",
    toolset="feishu_drive",
    schema=FEISHU_WIKI_LIST_SPACES_SCHEMA,
    handler=_handle_wiki_list_spaces,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="List wiki/knowledge-base spaces",
    emoji="\U0001f4da",
)

registry.register(
    name="feishu_wiki_create_node",
    toolset="feishu_drive",
    schema=FEISHU_WIKI_CREATE_NODE_SCHEMA,
    handler=_handle_wiki_create_node,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Create a node in a wiki/knowledge-base space",
    emoji="\U0001f4d6",
)
