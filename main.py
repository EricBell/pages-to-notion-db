#!/usr/bin/env python3
"""
Notion Journal Migration Script (with CLI via click)

Usage example:
  pip install notion-client requests python-dotenv click
  python migrate_notion_journal.py --pages-file pages.txt --notion-token $NOTION_TOKEN --target-db-id $TARGET_DB_ID

Features:
 - Accepts CLI args via click (pages file, notion token, target db id, rate sleep, dry-run, limit, verbose)
 - Dry-run mode simulates create/append steps (no writes) if --dry-run is set
 - Falls back to .env / environment variables for NOTION_TOKEN and TARGET_DB_ID
 - Test safely with --dry-run and/or --limit N
"""
import os
import re
import sys
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
from notion_client import Client
import click

# Globals set at runtime in main()
client = None
DRY_RUN = False
RATE_SLEEP = 0.35


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


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def fetch_all_children(block_id):
    """
    Recursively fetch all child blocks. Requires `client` to be initialized.
    """
    if client is None:
        raise RuntimeError("Notion client is not initialized; cannot fetch children.")
    children = []
    start_cursor = None
    batch_count = 0
    while True:
        batch_count += 1
        print(f"  -> Fetching blocks batch {batch_count}...")
        try:
            resp = client.blocks.children.list(block_id=block_id, start_cursor=start_cursor)
        except Exception as e:
            print(f"  -> Error fetching blocks: {e}")
            raise
        results = resp.get("results", [])
        print(f"  -> Got {len(results)} blocks in this batch")
        for r in results:
            if r.get("has_children"):
                r_copy = dict(r)
                print(f"  -> Recursing into block {r['id'][:8]}...")
                r_copy["_children"] = fetch_all_children(r["id"])
                children.append(r_copy)
            else:
                children.append(r)
        if not resp.get("next_cursor"):
            break
        start_cursor = resp.get("next_cursor")
        time.sleep(RATE_SLEEP)
    print(f"  -> Total blocks fetched: {len(children)}")
    return children


def plain_text_from_rich_text(rich_text_array):
    parts = []
    for rt in rich_text_array or []:
        parts.append(rt.get("plain_text", ""))
    return "".join(parts)


def convert_rich_text_item(rt):
    rt_type = rt.get("type", "text")
    
    # Handle different rich text types
    if rt_type == "text":
        new = {
            "type": "text",
            "text": {"content": rt.get("plain_text", "")}
        }
        if rt.get("href"):
            new["text"]["link"] = {"url": rt["href"]}
    elif rt_type == "mention":
        # Convert mentions to plain text to avoid validation issues
        new = {
            "type": "text", 
            "text": {"content": rt.get("plain_text", "")}
        }
    elif rt_type == "equation":
        # Convert equations to plain text
        new = {
            "type": "text",
            "text": {"content": rt.get("plain_text", "")}
        }
    else:
        # Fallback: convert unknown types to plain text
        new = {
            "type": "text",
            "text": {"content": rt.get("plain_text", "")}
        }
    
    # Add annotations if present
    annotations = rt.get("annotations", {})
    if annotations:
        new["annotations"] = {
            "bold": annotations.get("bold", False),
            "italic": annotations.get("italic", False),
            "strikethrough": annotations.get("strikethrough", False),
            "underline": annotations.get("underline", False),
            "code": annotations.get("code", False),
            "color": annotations.get("color", "default"),
        }
    return new


def convert_block_for_append(block):
    btype = block.get("type")
    base = {"object": "block", "type": btype}

    def _copy_rts(rt_arr):
        return [convert_rich_text_item(rt) for rt in rt_arr or []]

    if btype == "paragraph":
        base["paragraph"] = {"rich_text": _copy_rts(block["paragraph"].get("rich_text", []))}
    elif btype in ("heading_1", "heading_2", "heading_3"):
        base[btype] = {"rich_text": _copy_rts(block[btype].get("rich_text", []))}
    elif btype in ("bulleted_list_item", "numbered_list_item"):
        base[btype] = {"rich_text": _copy_rts(block[btype].get("rich_text", []))}
    elif btype == "to_do":
        base["to_do"] = {
            "rich_text": _copy_rts(block["to_do"].get("rich_text", [])),
            "checked": block["to_do"].get("checked", False),
        }
    elif btype == "quote":
        base["quote"] = {"rich_text": _copy_rts(block["quote"].get("rich_text", []))}
    elif btype == "code":
        base["code"] = {
            "rich_text": _copy_rts(block["code"].get("rich_text", [])),
            "language": block["code"].get("language", "plain text"),
        }
    elif btype == "callout":
        base["callout"] = {
            "rich_text": _copy_rts(block["callout"].get("rich_text", [])),
            "icon": block["callout"].get("icon"),
        }
    elif btype == "divider":
        base["divider"] = {}
    elif btype == "embed":
        base["embed"] = {"url": block["embed"].get("url")}
    elif btype == "image":
        image_obj = block.get("image", {})
        if "external" in image_obj and image_obj["external"].get("url"):
            base["image"] = {"type": "external", "external": {"url": image_obj["external"]["url"]}}
        elif "file" in image_obj and image_obj["file"].get("url"):
            base["image"] = {"type": "external", "external": {"url": image_obj["file"]["url"]}}
        else:
            base = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "[Image removed - original not accessible]"}}]}}
    elif btype == "file":
        file_obj = block.get("file", {})
        if "external" in file_obj and file_obj["external"].get("url"):
            base["file"] = {"type": "external", "external": {"url": file_obj["external"]["url"]}}
        elif "file" in file_obj and file_obj["file"].get("url"):
            base["file"] = {"type": "external", "external": {"url": file_obj["file"]["url"]}}
        else:
            base = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "[File removed - original not accessible]"}}]}}
    else:
        rt = None
        for key in ("paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"):
            if block.get(key) and block[key].get("rich_text"):
                rt = block[key]["rich_text"]
                break
        if rt:
            base = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _copy_rts(rt)}}
        else:
            base = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "[Unsupported block type copied as placeholder: " + str(btype) + "]"}}]}}
    if block.get("_children"):
        base["_children"] = [convert_block_for_append(c) for c in block["_children"]]
    return base


def guess_title_and_date_from_page(page_id):
    if client is None:
        raise RuntimeError("Notion client is not initialized; cannot guess title/date.")
    print(f"  -> Retrieving page metadata...")
    try:
        page = client.pages.retrieve(page_id=page_id)
    except Exception as e:
        print(f"  -> Error retrieving page: {e}")
        raise
    title = None
    date_iso = None

    props = page.get("properties", {})
    for k, v in props.items():
        if v.get("type") == "title":
            title_rts = v.get("title", [])
            title = plain_text_from_rich_text(title_rts).strip()
            if title:
                break

    if not title:
        children = client.blocks.children.list(block_id=page_id, page_size=50).get("results", [])
        for b in children:
            t = None
            for bt in ("heading_1", "heading_2", "heading_3", "paragraph"):
                if b.get(bt) and b[bt].get("rich_text"):
                    t = plain_text_from_rich_text(b[bt]["rich_text"]).strip()
                    break
            if t:
                title = t
                break

    if title:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
        if m:
            date_iso = m.group(1)
    if not date_iso:
        created = page.get("created_time")
        if created:
            try:
                date_iso = created.split("T")[0]
            except Exception:
                date_iso = created
    if not title:
        title = f"Imported page {page_id[:8]}"
    return title, date_iso


def create_database_page(title, date_iso):
    """
    Create a real DB page unless DRY_RUN is True, in which case simulate and return a fake id.
    """
    if DRY_RUN:
        fake_id = f"dryrun-{uuid.uuid4().hex[:8]}"
        print(f"[DRY-RUN] Would create DB page: Title={title!r}, Date={date_iso}, -> simulated id {fake_id}")
        return fake_id
    if client is None:
        raise RuntimeError("Notion client is not initialized; cannot create database page.")
    
    print(f"  -> Creating page in database {TARGET_DB_ID}...")
    
    # First, try to access the database to check permissions and structure
    try:
        print(f"  -> Checking database access...")
        db_info = client.databases.retrieve(database_id=TARGET_DB_ID)
        
        # Safely get database title
        db_title = "Unnamed"
        title_array = db_info.get('title', [])
        if title_array and len(title_array) > 0:
            db_title = title_array[0].get('plain_text', 'Unnamed')
        print(f"  -> Database found: {db_title}")
        
        # Check required properties exist
        db_props = db_info.get("properties", {})
        required_props = ["Title", "Date", "Archived"]
        missing_props = []
        for prop in required_props:
            if prop not in db_props:
                missing_props.append(prop)
        
        if missing_props:
            raise RuntimeError(f"Database missing required properties: {missing_props}. Found properties: {list(db_props.keys())}")
            
    except Exception as e:
        print(f"  -> Database access error: {e}")
        if "Could not find database" in str(e):
            print(f"  -> TROUBLESHOOTING STEPS:")
            print(f"     1. Verify database ID {TARGET_DB_ID} is correct")
            print(f"     2. Share the database with your integration")
            print(f"     3. Check the database isn't archived or deleted")
        raise
    
    properties = {
        "Title": {"title": [{"type": "text", "text": {"content": title}}]},
        "Date": {"date": {"start": date_iso}},
        "Archived": {"checkbox": False}
    }
    body = {"parent": {"database_id": TARGET_DB_ID}, "properties": properties}
    
    try:
        resp = client.pages.create(**body)
        print(f"  -> Successfully created page: {resp.get('id')}")
        return resp.get("id")
    except Exception as e:
        print(f"  -> Page creation failed: {e}")
        raise


def append_children_to_page(page_block_id, converted_children):
    """
    Append blocks to a page. If DRY_RUN, only report what would be appended.
    """
    if DRY_RUN:
        total = len(converted_children)
        print(f"[DRY-RUN] Would append {total} top-level block(s) to page {page_block_id}.")
        # Report nested counts roughly
        def count_all(blocks):
            c = 0
            for b in blocks:
                c += 1
                if b.get("_children"):
                    c += count_all(b["_children"])
            return c
        nested_total = count_all(converted_children)
        print(f"[DRY-RUN] Total blocks including nested: {nested_total}")
        return

    if client is None:
        raise RuntimeError("Notion client is not initialized; cannot append children.")

    for block in converted_children:
        block_copy = dict(block)
        nested = block_copy.pop("_children", None)
        if "object" in block_copy:
            block_copy.pop("object")
        resp = client.blocks.children.append(block_id=page_block_id, children=[block_copy])
        time.sleep(RATE_SLEEP)
        appended_ids = [r.get("id") for r in resp.get("results", []) if r.get("id")]
        if nested and appended_ids:
            parent_id = appended_ids[-1]
            append_children_to_page(parent_id, nested)


def migrate_page(source_page_id):
    try:
        click.echo(f"Starting migration for {source_page_id} ...")
        src_children = []
        if client is not None:
            src_children = fetch_all_children(source_page_id)
            time.sleep(RATE_SLEEP)
        else:
            if DRY_RUN:
                click.echo("  [DRY-RUN] No client available: skipping fetching children (simulation).")
            else:
                raise RuntimeError("Notion client required for migration but is not initialized.")

        title, date_iso = (None, None)
        if client is not None:
            title, date_iso = guess_title_and_date_from_page(source_page_id)
        else:
            if DRY_RUN:
                title = f"Simulated title for {source_page_id[:8]}"
                date_iso = datetime.utcnow().strftime("%Y-%m-%d")
            else:
                raise RuntimeError("Notion client required to guess title/date.")
        if not date_iso:
            date_iso = datetime.utcnow().strftime("%Y-%m-%d")
        click.echo(f"  -> Title: {title!r}, Date: {date_iso}")

        new_page_id = create_database_page(title, date_iso)
        click.echo(f"  -> Created new DB page: {new_page_id}")

        if src_children:
            converted = [convert_block_for_append(b) for b in src_children]
        else:
            converted = []
        append_children_to_page(new_page_id, converted)
        click.echo(f"  -> Appended {len(converted)} top-level blocks to {new_page_id}")
        return True
    except Exception as e:
        click.echo(f"ERROR migrating {source_page_id}: {e}", err=True)
        return False


@click.command()
@click.option("--pages-file", "-f", default="pages.txt", help="Path to file with Notion page URLs or IDs (one per line).")
@click.option("--notion-token", "-t", default=None, help="Notion integration token (env NOTION_TOKEN or provide here).")
@click.option("--target-db-id", "-d", default=None, help="Target Notion database id (env TARGET_DB_ID or provide here).")
@click.option("--rate-sleep", "-r", default=0.35, help="Seconds to sleep between API calls (reduce rate-limit risk).")
@click.option("--dry-run/--no-dry-run", default=False, help="If set, simulate actions without writing to Notion.")
@click.option("--limit", "-n", default=None, type=int, help="Optional: limit the number of pages to process (useful for testing).")
@click.option("--verbose/--no-verbose", default=False, help="Enable verbose logging.")
def main(pages_file, notion_token, target_db_id, rate_sleep, dry_run, limit, verbose):
    """
    CLI entrypoint for the migration script.
    """
    global client, DRY_RUN, RATE_SLEEP, TARGET_DB_ID
    load_dotenv()
    RATE_SLEEP = float(rate_sleep or os.getenv("RATE_SLEEP", 0.35))
    DRY_RUN = bool(dry_run)

    # Resolve token & db id: CLI > env > .env
    NOTION_TOKEN = notion_token or os.getenv("NOTION_TOKEN")
    TARGET_DB_ID = target_db_id or os.getenv("TARGET_DB_ID")

    if DRY_RUN:
        click.echo("[DRY-RUN MODE] No write operations will be performed.")
    else:
        if not NOTION_TOKEN:
            click.echo("ERROR: NOTION_TOKEN is required unless running with --dry-run.", err=True)
            sys.exit(1)
        if not TARGET_DB_ID:
            click.echo("ERROR: TARGET_DB_ID is required unless running with --dry-run.", err=True)
            sys.exit(1)

    if NOTION_TOKEN:
        client = Client(auth=NOTION_TOKEN)
        if verbose:
            click.echo("Notion client initialized.")

    if not os.path.exists(pages_file):
        click.echo(f"Pages file not found: {pages_file}", err=True)
        sys.exit(1)
    lines = read_lines(pages_file)
    if not lines:
        click.echo("No pages listed in pages file.")
        sys.exit(0)

    page_ids = []
    for line in lines:
        pid = extract_page_id(line)
        if not pid:
            click.echo(f"Skipping invalid line (no page id found): {line}", err=True)
            continue
        page_ids.append(pid)
    if limit:
        page_ids = page_ids[:limit]

    click.echo(f"Found {len(page_ids)} page(s) to migrate. Limit={limit or 'none'}. Rate_sleep={RATE_SLEEP}")

    succeeded = 0
    failed = 0
    for idx, pid in enumerate(page_ids, start=1):
        click.echo(f"\n[{idx}/{len(page_ids)}] Migrating {pid} ...")
        ok = migrate_page(pid)
        if ok:
            succeeded += 1
        else:
            failed += 1
        time.sleep(RATE_SLEEP)

    click.echo(f"\nMigration complete. Succeeded: {succeeded}, Failed: {failed}")


if __name__ == "__main__":
    main()