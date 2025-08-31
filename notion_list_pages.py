#!/usr/bin/env python3
"""
notion_list_pages.py

Create a pages file (pages.txt) for the migration script.

Modes:
 - parent: collect child pages under a parent page (recursively if requested)
 - database: list pages inside a database
 - search: search workspace for pages matching a query string

Usage examples:
  pip install notion-client python-dotenv click
  export NOTION_TOKEN="secret_xxx"
  python notion_list_pages.py --mode parent --parent-id YOUR_PARENT_PAGE_ID --output pages.txt
  python notion_list_pages.py --mode database --database-id YOUR_DB_ID --output pages_from_db.txt
  python notion_list_pages.py --mode search --query "journal" --output pages_found.txt --limit 500

Notes:
 - Integration must be invited to the source parent page / database / pages so it can read them.
 - Output contains one dashed page id per line (36-char).
"""
import os
import re
import time
from dotenv import load_dotenv
from notion_client import Client
import click

load_dotenv()

DEFAULT_RATE_SLEEP = 0.25


def extract_page_id(url_or_id: str):
    s = (url_or_id or "").strip()
    if not s:
        return None
    m = re.search(r"([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", s)
    if not m:
        return None
    raw = m.group(1)
    if "-" in raw:
        return raw
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def children_page_ids_from_parent(client, parent_id, recursive=True, rate_sleep=DEFAULT_RATE_SLEEP):
    """
    Walk the block children of parent_id and collect page ids for blocks of type 'child_page'.
    If recursive, will descend into child blocks to find nested pages.
    """
    collected = []
    stack = [parent_id]
    visited_blocks = set()

    while stack:
        block_id = stack.pop()
        start_cursor = None
        while True:
            resp = client.blocks.children.list(block_id=block_id, start_cursor=start_cursor, page_size=100)
            results = resp.get("results", [])
            for blk in results:
                blk_id = blk.get("id")
                if not blk_id or blk_id in visited_blocks:
                    continue
                visited_blocks.add(blk_id)
                btype = blk.get("type")
                if btype == "child_page":
                    # block id is the page id
                    collected.append(blk_id)
                elif btype == "child_database":
                    # this is a database block embedded - optionally skip or collect DB pages separately
                    # we do not add anything here automatically
                    pass
                # if recursive, push this block id to inspect its children too
                if recursive:
                    # only push blocks that can have children (many do)
                    if blk.get("has_children"):
                        stack.append(blk_id)
            if not resp.get("next_cursor"):
                break
            start_cursor = resp.get("next_cursor")
            time.sleep(rate_sleep)
    # dedupe preserve order
    seen = set()
    out = []
    for pid in collected:
        if pid not in seen:
            out.append(pid)
            seen.add(pid)
    return out


def pages_from_database(client, database_id, rate_sleep=DEFAULT_RATE_SLEEP):
    """
    Query a database and return page ids for all rows/pages in it.
    """
    collected = []
    start_cursor = None
    while True:
        resp = client.databases.query(database_id=database_id, start_cursor=start_cursor, page_size=100)
        for r in resp.get("results", []):
            pid = r.get("id")
            if pid:
                collected.append(pid)
        if not resp.get("next_cursor"):
            break
        start_cursor = resp.get("next_cursor")
        time.sleep(rate_sleep)
    return collected


def search_pages(client, query, rate_sleep=DEFAULT_RATE_SLEEP, limit=None):
    """
    Use client.search to find page objects across the workspace. Returns page ids.
    """
    collected = []
    start_cursor = None
    fetched = 0
    while True:
        resp = client.search(query=query or "", filter={"property": "object", "value": "page"}, start_cursor=start_cursor, page_size=100)
        for r in resp.get("results", []):
            pid = r.get("id")
            if pid:
                collected.append(pid)
                fetched += 1
                if limit and fetched >= limit:
                    return collected
        if not resp.get("next_cursor"):
            break
        start_cursor = resp.get("next_cursor")
        time.sleep(rate_sleep)
    return collected


@click.command()
@click.option("--mode", "-m", required=True, type=click.Choice(["parent", "database", "search"]), help="Mode: parent | database | search")
@click.option("--parent-id", "-p", default=None, help="Parent page id or URL (for mode=parent).")
@click.option("--database-id", "-d", default=None, help="Database id or URL (for mode=database).")
@click.option("--query", "-q", default=None, help="Search query (for mode=search).")
@click.option("--output", "-o", default="pages.txt", help="Output file (one page id per line).")
@click.option("--notion-token", "-t", default=None, help="Notion integration token (env NOTION_TOKEN or provide here).")
@click.option("--recursive/--no-recursive", default=True, help="If mode=parent, recurse into child blocks to find nested pages.")
@click.option("--rate-sleep", default=DEFAULT_RATE_SLEEP, help="Seconds to sleep between API calls.")
@click.option("--limit", default=None, type=int, help="Optional max number of pages to collect (useful for search or quick tests).")
def main(mode, parent_id, database_id, query, output, notion_token, recursive, rate_sleep, limit):
    load_dotenv()
    token = notion_token or os.getenv("NOTION_TOKEN")
    if not token:
        click.echo("ERROR: NOTION_TOKEN required (env or --notion-token). Invite the integration to source pages first.", err=True)
        raise SystemExit(1)

    client = Client(auth=token)
    page_ids = []

    if mode == "parent":
        if not parent_id:
            click.echo("ERROR: --parent-id required for mode=parent", err=True)
            raise SystemExit(1)
        pid = extract_page_id(parent_id)
        if not pid:
            click.echo("ERROR: could not extract parent id from the value provided", err=True)
            raise SystemExit(1)
        click.echo(f"Collecting child pages under parent {pid} (recursive={recursive})...")
        page_ids = children_page_ids_from_parent(client, pid, recursive=recursive, rate_sleep=rate_sleep)
    elif mode == "database":
        if not database_id:
            click.echo("ERROR: --database-id required for mode=database", err=True)
            raise SystemExit(1)
        dbid = extract_page_id(database_id)
        if not dbid:
            click.echo("ERROR: could not extract database id from the value provided", err=True)
            raise SystemExit(1)
        click.echo(f"Querying database {dbid} for pages...")
        page_ids = pages_from_database(client, dbid, rate_sleep=rate_sleep)
    elif mode == "search":
        if not query:
            click.echo("ERROR: --query required for mode=search", err=True)
            raise SystemExit(1)
        click.echo(f"Running workspace search for: {query!r} ...")
        page_ids = search_pages(client, query=query, rate_sleep=rate_sleep, limit=limit)
    else:
        click.echo("Unsupported mode", err=True)
        raise SystemExit(1)

    if limit:
        page_ids = page_ids[:limit]

    # Write output
    click.echo(f"Found {len(page_ids)} page(s). Writing to {output} ...")
    with open(output, "w", encoding="utf-8") as f:
        for pid in page_ids:
            f.write(pid + "\n")
    click.echo("Done.")