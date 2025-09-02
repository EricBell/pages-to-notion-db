# Notion Journal Migration Script

A Python CLI tool that migrates individual Notion pages into a structured database format, preserving content formatting and hierarchy.

## Features

- **Complete Content Migration**: Preserves text formatting, headings, lists, code blocks, images, files, and nested structures
- **CLI Interface**: Easy-to-use command-line interface with comprehensive options
- **Safety Features**: Dry-run mode for testing and rate limiting to avoid API limits
- **Flexible Authentication**: Support for environment variables or CLI arguments
- **Batch Processing**: Process multiple pages from a text file
- **Error Handling**: Robust error handling with detailed logging

## Installation

1. Install required dependencies:
```bash
pip install notion-client requests python-dotenv click
```

2. Set up your Notion integration:
   - Go to [Notion Integrations](https://www.notion.so/my-integrations)
   - Create a new integration and copy the token
   - Share your target database with the integration

## Configuration

### Environment Variables

1. Copy the example environment file:
```bash
cp env.example .env
```

2. Edit the `.env` file with your actual values:

```env
NOTION_TOKEN=your_notion_integration_token_here
TARGET_DB_ID=your_target_database_id_here
RATE_SLEEP=0.35
```

**Note**: The `env.example` file is provided as a template showing all required environment variables with placeholder values.

### Database Setup

Your target database should have these properties:
- **Title** (title property)
- **Date** (date property) 
- **Archived** (checkbox property)

## Usage

### Creating the Pages List

First, create a `pages.txt` file with page IDs using the companion script:

```bash
# List child pages under a parent page
python notion_list_pages.py --mode parent --parent-id YOUR_PARENT_PAGE_ID --output pages.txt

# List pages from a database
python notion_list_pages.py --mode database --database-id YOUR_DB_ID --output pages.txt

# Search for pages by query
python notion_list_pages.py --mode search --query "journal" --output pages.txt --limit 100
```

### Basic Migration

```bash
python main.py --pages-file pages.txt
```

### CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--pages-file` | `-f` | Path to file with Notion page URLs/IDs | `pages.txt` |
| `--notion-token` | `-t` | Notion integration token | From env |
| `--target-db-id` | `-d` | Target database ID | From env |
| `--rate-sleep` | `-r` | Sleep between API calls (seconds) | `0.35` |
| `--dry-run` | | Simulate without writing | `False` |
| `--limit` | `-n` | Limit number of pages to process | None |
| `--verbose` | | Enable verbose logging | `False` |

### Input File Format

Create a `pages.txt` file with one Notion page URL or ID per line:

```
https://www.notion.so/workspace/My-Journal-Entry-abc123def456
https://www.notion.so/workspace/Another-Page-789xyz012
def456abc123789xyz012345678901234567
```

## Examples

### Test Migration (Dry Run)

Test the migration without making changes:

```bash
python main.py --pages-file pages.txt --dry-run --verbose
```

### Limited Migration

Process only the first 5 pages:

```bash
python main.py --pages-file pages.txt --limit 5
```

### Custom Configuration

Override environment variables:

```bash
python main.py \
  --pages-file my-pages.txt \
  --notion-token secret_token \
  --target-db-id abc123 \
  --rate-sleep 0.5
```

### Verbose Migration

See detailed progress information:

```bash
python main.py --pages-file pages.txt --verbose
```

## How It Works

1. **Page Discovery**: Reads page URLs/IDs from the input file
2. **Content Extraction**: Fetches all blocks and child blocks from source pages
3. **Metadata Extraction**: Extracts title and date from page properties or content
4. **Database Creation**: Creates new entries in the target database
5. **Content Migration**: Converts and appends all blocks while preserving formatting

### Supported Block Types

- **Text**: Paragraphs with rich text formatting (bold, italic, links, etc.)
- **Headings**: H1, H2, H3 with formatting
- **Lists**: Bulleted and numbered lists
- **Code**: Code blocks with language syntax
- **Media**: Images and files (converted to external links)
- **Interactive**: To-do items with checked states
- **Layout**: Quotes, callouts, dividers
- **Nested**: Maintains parent-child block relationships

## Error Handling

The script includes comprehensive error handling:

- **Invalid URLs**: Skips malformed page URLs with warnings
- **API Errors**: Reports failed migrations but continues processing
- **Missing Files**: Clear error messages for missing input files
- **Authentication**: Validates tokens and database access

## Rate Limiting

To avoid Notion API rate limits:

- Default 350ms delay between API calls
- Configurable via `--rate-sleep` option
- Additional delays during bulk operations

## Development

### Project Structure

```
├── main.py                  # Main migration script
├── notion_list_pages.py     # Helper script to generate pages.txt
├── pages.txt               # Input file (page URLs/IDs)
├── .env                   # Environment variables
└── README.md             # This documentation
```

### Key Functions

**main.py**:
- `extract_page_id()`: Parses Notion URLs to extract page IDs
- `fetch_all_children()`: Recursively fetches all block content
- `convert_block_for_append()`: Converts blocks for database insertion
- `migrate_page()`: Main migration logic for individual pages

**notion_list_pages.py**:
- `children_page_ids_from_parent()`: Collects child pages from a parent page
- `pages_from_database()`: Extracts all pages from a database
- `search_pages()`: Searches workspace for pages matching a query

## Troubleshooting

### Common Issues

**"NOTION_TOKEN is required"**
- Set token in `.env` file or use `--notion-token` option
- Ensure integration has access to source pages and target database

**"Pages file not found"**
- Check file path and ensure `pages.txt` exists
- Use `--pages-file` to specify different file

**"Invalid page ID"**
- Verify page URLs are properly formatted
- Ensure pages are accessible by the integration

**Rate Limiting**
- Increase `--rate-sleep` value if getting rate limited
- Use smaller batches with `--limit` option

### Debug Tips

1. Start with `--dry-run` to test configuration
2. Use `--limit 1` to test single page migration
3. Enable `--verbose` for detailed logging
4. Check integration permissions in Notion

## License

This project is open source. Feel free to modify and distribute.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with dry-run mode
5. Submit a pull request

## Support

For issues and questions:
1. Check the troubleshooting section
2. Verify your Notion integration setup
3. Test with dry-run mode first
4. Review error messages for specific guidance