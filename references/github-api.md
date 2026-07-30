# GitHub API Endpoints Used by People Helper

## Authentication

All requests use a fine-grained PAT in the `Authorization: Bearer {token}` header.

## Endpoints

### `GET /user`
- **Purpose:** Verify PAT is valid and check scope type
- **Expected:** 200 (user JSON) or 401/403 (bad token)
- **Rate cost:** 1 request

### `GET /search/repositories`
- **Purpose:** Find similar open source projects for each candidate
- **Query params:** `q={keywords}+language:{lang}+stars:>=5+pushed:>=YYYY-MM-DD`, `sort=stars`, `per_page=5`
- **Expected:** 200 (items array) or 403 (rate limited) or 422 (validation error)
- **Rate cost:** 1 request per candidate
- **Fields used:** `full_name`, `html_url`, `stargazers_count`, `forks_count`, `open_issues_count`, `description`, `pushed_at`, `license.spdx_id`, `language`

## Rate limits

- Authenticated: 5,000 requests/hour
- People Helper uses ~1 (auth) + N (candidates) requests
- On 403: stops and reports to user

## Headers sent

```
Authorization: Bearer {token}
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```