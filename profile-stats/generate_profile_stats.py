#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a GitHub profile stats SVG card without depending on github-readme-stats.vercel.app.

Usage:
  USERNAME=xingfengwxx GH_TOKEN=*** python profile-stats/generate_profile_stats.py
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

USERNAME = os.getenv("USERNAME", "xingfengwxx").strip()
TOKEN = os.getenv("GH_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
OUTPUT = os.getenv("OUTPUT", "profile-stats.svg").strip()


class ApiError(RuntimeError):
    pass


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    h = {
        "Accept": accept,
        "User-Agent": "profile-stats-card-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def _request_json(url: str, accept: str = "application/vnd.github+json") -> tuple[Any, dict[str, str]]:
    req = urllib.request.Request(url, headers=_headers(accept))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return json.loads(body), headers
    except Exception as e:
        raise ApiError(f"Request failed: {url}\n{e}") from e


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=data,
        method="POST",
        headers={**_headers("application/json"), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        raise ApiError(f"GraphQL request failed: {e}") from e

    if payload.get("errors"):
        raise ApiError(f"GraphQL errors: {payload['errors']}")
    return payload.get("data", {})


def _parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        sec = part.strip()
        if 'rel="next"' in sec:
            m = re.search(r"<([^>]+)>", sec)
            if m:
                return m.group(1)
    return None


def _humanize(n: int) -> str:
    if n >= 1_000_000:
        text = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}m"
    if n >= 1_000:
        text = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    return str(n)


def _grade(stars: int, commits: int, prs: int, issues: int, contributed_to: int) -> str:
    score = (
        stars * 0.03
        + commits * 0.004
        + prs * 0.12
        + issues * 0.06
        + contributed_to * 0.8
    )
    score = max(0.0, min(100.0, score))

    if score >= 90:
        return "A++"
    if score >= 80:
        return "A+"
    if score >= 70:
        return "A"
    if score >= 60:
        return "B+"
    if score >= 50:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _rest_count(path: str, query: dict[str, str], accept: str = "application/vnd.github+json") -> int:
    params = urllib.parse.urlencode(query)
    url = f"{API_BASE}{path}?{params}"
    data, _ = _request_json(url, accept=accept)
    return int(data.get("total_count", 0))


def _fetch_stats_rest(username: str) -> dict[str, int]:
    # 1) total stars from owned repos (non-fork)
    stars = 0
    url = f"{API_BASE}/users/{username}/repos?per_page=100&type=owner&sort=updated"
    while url:
        repos, headers = _request_json(url)
        for repo in repos:
            if not repo.get("fork", False):
                stars += int(repo.get("stargazers_count", 0))
        url = _parse_next_link(headers.get("link"))

    # 2) totals from search API
    commits = _rest_count(
        "/search/commits",
        {"q": f"author:{username}", "per_page": "1"},
        accept="application/vnd.github.cloak-preview+json",
    )
    prs = _rest_count(
        "/search/issues",
        {"q": f"author:{username} type:pr", "per_page": "1"},
    )
    issues = _rest_count(
        "/search/issues",
        {"q": f"author:{username} type:issue -type:pr", "per_page": "1"},
    )

    # 3) contributed_to (approx): unique repositories from public events (max 300 events)
    repos = set()
    for page in range(1, 11):
        events, _ = _request_json(f"{API_BASE}/users/{username}/events/public?per_page=30&page={page}")
        if not events:
            break
        for e in events:
            repo = e.get("repo", {}).get("name")
            if repo:
                repos.add(repo)

    return {
        "stars": stars,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "contributed_to": len(repos),
    }


def _fetch_stats_graphql(username: str) -> dict[str, int]:
    # Better accuracy if token is available.
    stars = 0
    cursor = None
    query_repos = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, after: $cursor) {
          nodes { stargazerCount }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """

    while True:
        data = _graphql(query_repos, {"login": username, "cursor": cursor})
        user = data.get("user")
        if not user:
            raise ApiError(f"User not found: {username}")
        repos = user["repositories"]
        for node in repos.get("nodes", []):
            stars += int(node.get("stargazerCount", 0))

        page_info = repos.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    now = dt.datetime.utcnow()
    one_year_ago = now - dt.timedelta(days=365)

    query_contrib = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalRepositoriesWithContributedCommits
        }
      }
    }
    """

    data = _graphql(
        query_contrib,
        {
            "login": username,
            "from": one_year_ago.replace(microsecond=0).isoformat() + "Z",
            "to": now.replace(microsecond=0).isoformat() + "Z",
        },
    )
    cc = data.get("user", {}).get("contributionsCollection", {})

    return {
        "stars": stars,
        "commits": int(cc.get("totalCommitContributions", 0)),
        "prs": int(cc.get("totalPullRequestContributions", 0)),
        "issues": int(cc.get("totalIssueContributions", 0)),
        "contributed_to": int(cc.get("totalRepositoriesWithContributedCommits", 0)),
    }


def _svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_svg(username: str, stars: int, commits: int, prs: int, issues: int, contributed_to: int) -> str:
    grade = _grade(stars, commits, prs, issues, contributed_to)

    title = f"{username}'s GitHub Stats"

    rows = [
        ("✦", "Total Stars:", _humanize(stars)),
        ("◷", "Total Commits:", _humanize(commits)),
        ("⑂", "Total PRs:", _humanize(prs)),
        ("◉", "Total Issues:", _humanize(issues)),
        ("▣", "Contributed to:", _humanize(contributed_to)),
    ]

    width = 495
    height = 210

    row_svg = []
    base_y = 66
    row_h = 27
    for idx, (icon, label, value) in enumerate(rows):
        y = base_y + idx * row_h
        row_svg.append(
            f'''
      <text x="24" y="{y}" class="icon">{_svg_escape(icon)}</text>
      <text x="50" y="{y}" class="label">{_svg_escape(label)}</text>
            <text x="210" y="{y}" class="value" text-anchor="end">{_svg_escape(value)}</text>
'''
        )

    updated = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{_svg_escape(title)}</title>
  <desc id="desc">Auto-generated GitHub profile stats card.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0D1117"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#8B5CF6"/>
      <stop offset="100%" stop-color="#2F81F7"/>
    </linearGradient>
    <style>
      .title {{ fill: #58A6FF; font: 700 33px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .icon {{ fill: #C792EA; font: 600 18px 'Segoe UI Symbol', 'Segoe UI', Ubuntu, Sans-Serif; }}
      .label {{ fill: #31C6B8; font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .value {{ fill: #31C6B8; font: 700 18px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .grade {{ fill: #31C6B8; font: 700 45px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .meta {{ fill: #6E7681; font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    </style>
  </defs>

    <rect x="1" y="1" width="493" height="208" rx="12" fill="url(#bg)" stroke="#30363D"/>
  <text x="24" y="40" class="title">{_svg_escape(title)}</text>

  {''.join(row_svg)}

  <circle cx="402" cy="98" r="48" fill="none" stroke="#263B6B" stroke-width="8"/>
  <circle cx="402" cy="98" r="48" fill="none" stroke="url(#ring)" stroke-width="8" stroke-linecap="round"/>
  <text x="402" y="108" text-anchor="middle" class="grade">{_svg_escape(grade)}</text>

    <text x="24" y="198" class="meta">Updated: {_svg_escape(updated)}</text>
</svg>
'''


def main() -> None:
    if not USERNAME:
        raise SystemExit("USERNAME is required")

    stats = None

    if TOKEN:
        try:
            stats = _fetch_stats_graphql(USERNAME)
            print("Fetched stats via GraphQL")
        except Exception as e:
            print(f"GraphQL failed, fallback to REST: {e}")

    if stats is None:
        stats = _fetch_stats_rest(USERNAME)
        print("Fetched stats via REST")

    svg = build_svg(
        USERNAME,
        stats["stars"],
        stats["commits"],
        stats["prs"],
        stats["issues"],
        stats["contributed_to"],
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {OUTPUT}")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
