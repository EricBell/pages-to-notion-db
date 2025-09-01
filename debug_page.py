from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv()
client = Client(auth=os.getenv('NOTION_TOKEN'))

page_id = "2618b6c8a9a4806aac35fbd1403677b3"

# Try to get page info
try:
    page = client.pages.retrieve(page_id=page_id)
    print(f"✅ This is a PAGE")
    print(f"Title: {page.get('properties', {}).get('title', 'No title')}")
    
    # Check if it has children
    children = client.blocks.children.list(block_id=page_id, page_size=10)
    child_count = len(children.get('results', []))
    print(f"Child blocks: {child_count}")
    
    # Show child types
    for child in children.get('results', []):
        child_type = child.get('type')
        print(f"  - Child type: {child_type}")
        if child_type == 'child_page':
            print(f"    Page title: {child.get('child_page', {}).get('title', 'Untitled')}")
            
except Exception as e:
    print(f"❌ Not a page: {e}")

# Try as database
try:
    db = client.databases.retrieve(database_id=page_id) 
    print(f"✅ This is a DATABASE")
    print(f"Title: {db.get('title', [{}])[0].get('plain_text', 'Unnamed')}")
except Exception as e:
    print(f"❌ Not a database: {e}")