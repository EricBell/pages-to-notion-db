from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv()
client = Client(auth=os.getenv('NOTION_TOKEN'))
db = client.databases.retrieve('2608b6c8a9a480a8b449e58874a8c536')
print('Properties:', list(db['properties'].keys()))