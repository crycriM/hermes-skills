---
name: z-ai-web-reader-mcp
title: Z.ai Web Reader MCP
category: mcp
description: |
  Streamable-http MCP server that fetches URLs and returns model-friendly
  Markdown or plain text. Used for scraping SSRN, arXiv, or any web page
  into a format downstream LLMs can consume.
---

# Z.ai Web Reader MCP

## Endpoint
```
https://api.z.ai/api/mcp/web_reader/mcp
```
Type: `streamable-http`  
Auth: Bearer token in `Authorization` header

## Function: `webReader`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | required | URL to fetch |
| `return_format` | string | `markdown` | `markdown` or `text` |
| `retain_images` | bool | `false` | Return image data-URIs |
| `no_gfm` | bool | `false` | Disable GitHub-flavored markdown |
| `keep_img_data_url` | bool | `false` | Keep images as data URLs |
| `with_images_summary` | bool | `false` | Include images summary |
| `with_links_summary` | bool | `false` | Include links summary |

## SKILL.md Frontmatter Rule
**Every SKILL.md MUST have `name:` field in YAML frontmatter**, or `skill_manage create` fails with:
```
Frontmatter must include 'name' field
```
Minimum valid frontmatter:
```yaml
---
name: skill-name
title: Skill Title
category: mcp
description: |
  One-line description.
---
```

## Skill Creation Fix
When `skill_manage` fails because SKILL.md lacks `name:`:
1. Create dir: `mkdir -p ~/.hermes/skills/<skill-name>`
2. Write SKILL.md with proper frontmatter including `name: <skill-name>`
3. Verify with `skill_view name=<skill-name>`

## Usage Example (Python)
```python
from hermes_tools import mcp_web_reader_webReader

result = mcp_web_reader_webReader(
    url = f'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5995614',
    return_format = 'markdown',
    retain_images = False,
)
print(result.get('content', ''))
```

## Testing
- SSRN test URL: `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5995614`
- OpenAlex lookup first for DOI → SSRN ID mapping