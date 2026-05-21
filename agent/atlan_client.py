"""Read-only Atlan REST client for discovery context priming.

Discovery queries Atlan at session start to establish what's already known
about the customer's domain. The fetched context becomes a section in the
mega-agent's system prompt — definitions don't get re-asked, table schemas
are taken as given, lineage informs root-cause-style skill design.

Scope: READ only. Write-back is deferred (see
docs/internal/plans/06-atlan-context-integration.md §"deferred write-back").

Transport: pure httpx against Atlan's REST API. No pyatlan dependency —
discovery-inception is a thin tool, not an Atlan workflow app. Keeping the
client to httpx + the documented endpoints avoids the ~150MB pyatlan
install and lets the project work against any tenant the user has an API
key for.

Graceful degradation is a hard requirement: discovery NEVER blocks on
Atlan availability. Auth missing / tenant unreachable / scope empty all
return a `BoundedContext` with a `fetch_status` reflecting the situation
and the conversation proceeds in probe-only mode.

Endpoints used:
  POST /api/meta/search/indexsearch        glossary terms + tables + tags
  GET  /api/meta/types                     (reserved for term-asset lineage)
  POST /api/meta/lineage/list              upstream/downstream relations

Atlan's index-search payload syntax follows their Elasticsearch-style DSL.
We construct minimal queries; users can extend by passing extra filters
via the `extra_filters` argument once the API stabilizes.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from agent.atlan_context import (
    BoundedContext,
    BusinessDomain,
    GlossaryTerm,
    LineageEdge,
    LineageGraph,
    Ownership,
    Tag,
    TableColumn,
    TableDefinition,
)


# ---------------------------------------------------------------------------
# Auth / config
# ---------------------------------------------------------------------------


def _resolve_base_url(tenant: str | None) -> str | None:
    """Build the base URL from a CLI tenant arg or fall back to env.

    `tenant` may be 'ces.atlan.com' (bare host) or 'https://ces.atlan.com'
    (fully-qualified). Bare hosts get https:// prepended.
    """
    if tenant:
        if tenant.startswith("http://") or tenant.startswith("https://"):
            return tenant.rstrip("/")
        return f"https://{tenant.rstrip('/')}"
    env = os.environ.get("ATLAN_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    return None


def _resolve_api_key() -> str | None:
    return (os.environ.get("ATLAN_API_KEY") or "").strip() or None


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


async def _search(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST /api/meta/search/indexsearch and return parsed JSON.

    Raises httpx exceptions on transport failure; caller is responsible for
    catching and converting to a `BoundedContext.fetch_status='error'`.
    """
    url = f"{base_url}/api/meta/search/indexsearch"
    resp = await client.post(url, json=payload, headers=_auth_headers(api_key))
    resp.raise_for_status()
    return resp.json()


def _ownership_from_entity(entity: dict[str, Any]) -> dict[str, str | None]:
    """Pull ownerUsers / certifiers / stewards from an entity attributes block."""
    attrs = entity.get("attributes", {}) or {}
    owners = attrs.get("ownerUsers") or []
    stewards = attrs.get("assetUserDefinedType") or []  # placeholder; tenants vary
    certifier = attrs.get("certificateUpdatedBy")
    return {
        "owner": ", ".join(owners) if owners else None,
        "steward": ", ".join(stewards) if stewards else None,
        "certifier": certifier,
    }


def _classify_tag(tag_name: str) -> str:
    lower = tag_name.lower()
    if "pii" in lower or "personal" in lower:
        return "pii"
    if "certif" in lower or "verified" in lower or "quality" in lower:
        return "certified_quality"
    if "compli" in lower or "sox" in lower or "gdpr" in lower or "hipaa" in lower:
        return "compliance"
    return "other"


# ---------------------------------------------------------------------------
# Slot fetchers — each is best-effort; on error the slot stays empty
# ---------------------------------------------------------------------------


async def _fetch_glossary_terms(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    glossary: str,
    *,
    limit: int = 100,
) -> list[GlossaryTerm]:
    """Search AtlasGlossaryTerm filtered by parent glossary name."""
    payload = {
        "dsl": {
            "size": limit,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"__typeName.keyword": "AtlasGlossaryTerm"}},
                        {"term": {"__state": "ACTIVE"}},
                    ],
                    "must": [
                        {"match": {"anchor.displayText": glossary}},
                    ],
                }
            },
        },
        "attributes": [
            "name",
            "qualifiedName",
            "userDescription",
            "shortDescription",
            "anchor",
            "categories",
        ],
    }
    try:
        data = await _search(client, base_url, api_key, payload)
    except Exception:
        return []
    out: list[GlossaryTerm] = []
    for ent in data.get("entities") or []:
        attrs = ent.get("attributes") or {}
        defn = (
            attrs.get("userDescription")
            or attrs.get("shortDescription")
            or ent.get("displayText")
        )
        out.append(
            GlossaryTerm(
                name=attrs.get("name") or ent.get("displayText") or "(unnamed)",
                qualified_name=attrs.get("qualifiedName"),
                definition=defn,
                glossary=glossary,
                category=(
                    (attrs.get("categories") or [{}])[0].get("displayText")
                    if attrs.get("categories")
                    else None
                ),
            )
        )
    return out


async def _fetch_tables(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    table_qns: list[str],
) -> tuple[list[TableDefinition], list[Ownership], list[Tag]]:
    """Look up the given table QNs; pull description + columns + ownership + tags.

    We resolve columns in a second pass when the first response only carries
    relation pointers (Atlan's default behavior).
    """
    if not table_qns:
        return [], [], []

    payload = {
        "dsl": {
            "size": len(table_qns) * 2,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"__typeName.keyword": ["Table", "View"]}},
                        {"terms": {"qualifiedName": table_qns}},
                    ]
                }
            },
        },
        "attributes": [
            "name",
            "qualifiedName",
            "description",
            "userDescription",
            "rowCount",
            "ownerUsers",
            "classificationNames",
        ],
        "relationAttributes": ["name", "dataType", "description"],
    }
    try:
        data = await _search(client, base_url, api_key, payload)
    except Exception:
        return [], [], []

    tables: list[TableDefinition] = []
    ownerships: list[Ownership] = []
    tags: list[Tag] = []

    for ent in data.get("entities") or []:
        attrs = ent.get("attributes") or {}
        name = attrs.get("name") or "(unnamed)"
        qn = attrs.get("qualifiedName") or ""
        desc = attrs.get("userDescription") or attrs.get("description")
        cols_raw = (
            attrs.get("columns")
            or ent.get("relationshipAttributes", {}).get("columns")
            or []
        )
        cols: list[TableColumn] = []
        for c in cols_raw:
            c_attrs = (c.get("attributes") or {}) if isinstance(c, dict) else {}
            cols.append(
                TableColumn(
                    name=c_attrs.get("name") or c.get("displayText", "(col)"),
                    data_type=c_attrs.get("dataType"),
                    description=c_attrs.get("description"),
                )
            )
        tables.append(
            TableDefinition(
                name=name,
                qualified_name=qn,
                description=desc,
                columns=cols,
                row_count=attrs.get("rowCount"),
            )
        )

        own = _ownership_from_entity(ent)
        if any(own.values()):
            ownerships.append(
                Ownership(asset_qn=qn, asset_name=name, **own)
            )

        for tag_name in attrs.get("classificationNames") or []:
            tags.append(
                Tag(
                    asset_qn=qn,
                    asset_name=name,
                    tag_name=tag_name,
                    classification=_classify_tag(tag_name),  # type: ignore[arg-type]
                )
            )

    return tables, ownerships, tags


async def _fetch_lineage(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    asset_qns: list[str],
    *,
    depth: int = 2,
) -> LineageGraph:
    """Pull lineage relations for the given assets. Best-effort.

    Atlan's lineage endpoint requires guid not QN in some versions; we
    skip lineage entirely if the lookup fails — it's a nice-to-have, not
    load-bearing for discovery.
    """
    if not asset_qns:
        return LineageGraph()
    # Stub: most tenants gate lineage behind /api/meta/lineage/list with a
    # specific request shape that differs across versions. We attempt a
    # minimal call and fall back to empty if it errors.
    edges: list[LineageEdge] = []
    for qn in asset_qns:
        url = f"{base_url}/api/meta/lineage/list"
        payload = {
            "qualifiedName": qn,
            "direction": "BOTH",
            "depth": depth,
            "size": 50,
        }
        try:
            resp = await client.post(url, json=payload, headers=_auth_headers(api_key))
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        for rel in data.get("relations") or []:
            up = rel.get("fromEntityId") or rel.get("upstream_qn")
            down = rel.get("toEntityId") or rel.get("downstream_qn")
            if up and down:
                edges.append(
                    LineageEdge(
                        upstream_qn=up,
                        downstream_qn=down,
                        edge_type="other",
                    )
                )
    return LineageGraph(edges=edges)


async def _fetch_business_domains(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    domain_names: list[str],
) -> list[BusinessDomain]:
    """Look up DataDomain assets by name; return descriptions + asset counts."""
    if not domain_names:
        return []
    payload = {
        "dsl": {
            "size": len(domain_names) * 2,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"__typeName.keyword": "DataDomain"}},
                    ],
                    "must": [
                        {"terms": {"name.keyword": domain_names}},
                    ],
                }
            },
        },
        "attributes": ["name", "description", "userDescription"],
    }
    try:
        data = await _search(client, base_url, api_key, payload)
    except Exception:
        return []
    out: list[BusinessDomain] = []
    for ent in data.get("entities") or []:
        attrs = ent.get("attributes") or {}
        out.append(
            BusinessDomain(
                name=attrs.get("name") or "(unnamed)",
                description=attrs.get("userDescription") or attrs.get("description"),
                n_assets=None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_bounded_context(
    *,
    tenant: str | None = None,
    glossary: str | None = None,
    tables: list[str] | None = None,
    domains: list[str] | None = None,
    timeout_s: float = 15.0,
) -> BoundedContext:
    """Pull a structured snapshot of what Atlan knows about the given scope.

    Returns a populated `BoundedContext` on success, an empty one with
    `fetch_status='empty'` when the scope is reachable but uncatalogued,
    or `fetch_status='error'` when Atlan is unavailable.

    Discovery NEVER blocks on this call. Total budget is `timeout_s`; if we
    blow through it, the established-context block in the prompt notes the
    failure and discovery proceeds in probe-only mode.
    """
    base_url = _resolve_base_url(tenant)
    api_key = _resolve_api_key()

    if not base_url or not api_key:
        missing = []
        if not base_url:
            missing.append("ATLAN_BASE_URL (or --atlan-tenant)")
        if not api_key:
            missing.append("ATLAN_API_KEY")
        return BoundedContext(
            source_tenant=tenant or "(unconfigured)",
            fetch_status="not_configured",
            error_message=f"Missing: {', '.join(missing)}.",
            scope_glossary=glossary,
            scope_tables=list(tables or []),
            scope_domains=list(domains or []),
        )

    ctx = BoundedContext(
        source_tenant=tenant or base_url.replace("https://", "").replace("http://", ""),
        fetch_status="empty",
        scope_glossary=glossary,
        scope_tables=list(tables or []),
        scope_domains=list(domains or []),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            jobs: list[asyncio.Future] = []
            if glossary:
                jobs.append(_fetch_glossary_terms(client, base_url, api_key, glossary))
            if tables:
                jobs.append(_fetch_tables(client, base_url, api_key, list(tables)))
            if domains:
                jobs.append(
                    _fetch_business_domains(client, base_url, api_key, list(domains))
                )

            results = await asyncio.gather(*jobs, return_exceptions=True)

            cursor = 0
            if glossary:
                r = results[cursor]
                cursor += 1
                if not isinstance(r, Exception):
                    ctx.glossary_terms = r
            if tables:
                r = results[cursor]
                cursor += 1
                if not isinstance(r, Exception):
                    tbls, owns, tgs = r
                    ctx.tables = tbls
                    ctx.ownership.extend(owns)
                    ctx.tags.extend(tgs)
                    # Lineage uses table QNs — fire only after tables landed.
                    qns = [t.qualified_name for t in tbls if t.qualified_name]
                    if qns:
                        ctx.lineage = await _fetch_lineage(client, base_url, api_key, qns)
            if domains:
                r = results[cursor]
                cursor += 1
                if not isinstance(r, Exception):
                    ctx.business_domains = r
    except Exception as exc:
        ctx.fetch_status = "error"
        ctx.error_message = f"{type(exc).__name__}: {exc}"
        return ctx

    ctx.fetch_status = "populated" if ctx.is_populated() else "empty"
    return ctx


async def search_glossary(
    *,
    tenant: str | None,
    query: str,
    limit: int = 10,
    timeout_s: float = 10.0,
) -> list[GlossaryTerm]:
    """Free-text search across glossary terms.

    Used when discovery surfaces a concept mid-conversation that wasn't in
    the initial bounded-context fetch. Exposed as a runtime tool to the
    mega-agent in a later iteration; for now it's available for ad-hoc use.
    """
    base_url = _resolve_base_url(tenant)
    api_key = _resolve_api_key()
    if not base_url or not api_key:
        return []
    payload = {
        "dsl": {
            "size": limit,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"__typeName.keyword": "AtlasGlossaryTerm"}},
                        {"term": {"__state": "ACTIVE"}},
                    ],
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "userDescription", "shortDescription"],
                            }
                        }
                    ],
                }
            },
        },
        "attributes": [
            "name",
            "qualifiedName",
            "userDescription",
            "shortDescription",
            "anchor",
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            data = await _search(client, base_url, api_key, payload)
    except Exception:
        return []
    out: list[GlossaryTerm] = []
    for ent in data.get("entities") or []:
        attrs = ent.get("attributes") or {}
        out.append(
            GlossaryTerm(
                name=attrs.get("name") or "(unnamed)",
                qualified_name=attrs.get("qualifiedName"),
                definition=attrs.get("userDescription") or attrs.get("shortDescription"),
                glossary=(attrs.get("anchor") or {}).get("displayText"),
            )
        )
    return out
