# People Helper — GitHub API Reference

The skill uses these GitHub REST API endpoints. All calls are read-only.

## Authentication

```http
Authorization: Bearer ${PEOPLE_HELPER_PAT}
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

The PAT must be fine-grained with `Contents: Read` and `Metadata: Read` only.

## Endpoints

### Verify PAT and identify user

```
GET https://api.github.com/user
```

Response (200):
```json
{
  "login": "username",
  "id": 12345,
  "type": "User"
}
```

Headers to check:
- `x-oauth-scopes`: For classic PATs, comma-separated scopes. Should NOT contain `repo` or `admin:*` for People Helper. Fine-grained PATs return empty.
- `x-ratelimit-limit`: 5000 for authenticated users
- `x-ratelimit-remaining`: how many requests left in the current window
- `x-ratelimit-reset`: Unix timestamp when the window resets

### Walk a private repo's contents

For private repos, shallow-clone locally (preferred) or walk via API:

```
GET https://api.github.com/repos/{owner}/{name}/contents/{path}
```

Response (200):
```json
[
  {
    "name": "README.md",
    "path": "README.md",
    "type": "file",
    "size": 1024,
    "download_url": "https://raw.githubusercontent.com/..."
  }
]
```

Recursion: walk the tree by following `"type": "dir"` entries. Note this is slow for large repos (one API call per directory).

**Recommended**: Use `git clone --depth 1` for private repos. Faster, no rate limit hit.

### Search repositories

```
GET https://api.github.com/search/repositories?q={query}+language:{lang}+stars:>={min_stars}&sort=stars&per_page=5
```

Query syntax:
- `language:python` — restrict to language
- `stars:>=5` — minimum stars
- Free text — matches repo name, description, README

Sort options: `stars` (default), `forks`, `help-wanted-issues`, `updated`.

Response (200):
```json
{
  "total_count": 1234,
  "items": [
    {
      "full_name": "owner/repo",
      "html_url": "https://github.com/owner/repo",
      "description": "...",
      "stargazers_count": 100,
      "pushed_at": "2026-01-15T00:00:00Z",
      "license": {"spdx_id": "MIT"}
    }
  ]
}
```

Rate limit: 30 requests/minute for search (much lower than regular API).

### Get a repo's README

```
GET https://api.github.com/repos/{owner}/{name}/readme
```

Response (200):
```json
{
  "name": "README.md",
  "content": "base64-encoded content",
  "encoding": "base64"
}
```

Decode the base64 `content` field to get the README text. Truncate to first 500 chars for the report.

## Rate limit strategy

People Helper makes roughly:
- 1 call: verify PAT
- 0 calls: shallow-clone the user's repo (no API)
- 3-5 calls per candidate: search + 5 README fetches
- ~50 calls total for 10 candidates

Well under the 5000/hour limit for authenticated users. The search-specific limit of 30/min is the tighter constraint — don't search more than ~5 candidates per minute.

If you hit a 403:
1. Check `x-ratelimit-remaining` header (should be 0)
2. Check `x-ratelimit-reset` header for when to retry
3. If it's the search-specific limit, wait 60 seconds
4. If it's the global limit, stop and tell the user

## Safety reminders

- **Never use POST, PUT, PATCH, DELETE.** Only GET. The skill is read-only.
- **Never include the PAT in URLs you log or display.** Use the Authorization header, not query params.
- **Never share the user's code in API calls.** Only the file paths and search queries.
- **Always clean up the temp clone** after analysis, even on error.
