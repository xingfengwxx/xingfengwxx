#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a GitHub top languages SVG card without depending on github-readme-stats.vercel.app.

Usage:
  USERNAME=xingfengwxx GH_TOKEN=*** python profile-stats/generate_top_languages.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
from typing import Any

API_BASE = "https://api.github.com"

USERNAME = (
    os.getenv("GH_USERNAME", "").strip()
    or os.getenv("GITHUB_USERNAME", "").strip()
    or "xingfengwxx"
)
TOKEN = os.getenv("GH_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "top-langs.svg")
OUTPUT = os.getenv("OUTPUT", "").strip() or DEFAULT_OUTPUT


class ApiError(RuntimeError):
    pass


def _headers(use_token: bool = True) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "top-languages-card-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN and use_token:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def _request_json(url: str, use_token: bool = True) -> tuple[Any, dict[str, str]]:
    req = urllib.request.Request(url, headers=_headers(use_token=use_token))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return json.loads(body), headers
    except Exception as e:
        raise ApiError(f"Request failed: {url}\n{e}") from e


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


def _svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _fetch_repo_languages(username: str) -> dict[str, int]:
    detailed_totals: dict[str, int] = {}
    primary_totals: dict[str, int] = {}

    def _collect(use_token: bool) -> bool:
        url = f"{API_BASE}/users/{username}/repos?per_page=100&type=owner&sort=updated"
        while url:
            try:
                repos, headers = _request_json(url, use_token=use_token)
            except ApiError:
                # If authenticated request fails at repo list level, caller can retry unauthenticated.
                return False

            for repo in repos:
                if repo.get("fork", False):
                    continue
                if repo.get("archived", False):
                    continue

                primary = (repo.get("language") or "").strip()
                if primary:
                    primary_totals[primary] = primary_totals.get(primary, 0) + 1

                # Detailed language byte stats are best-effort only.
                if not (TOKEN and use_token):
                    continue

                lang_url = repo.get("languages_url")
                if not lang_url:
                    continue

                try:
                    langs, _ = _request_json(lang_url, use_token=True)
                except ApiError:
                    continue

                for name, size in langs.items():
                    detailed_totals[name] = detailed_totals.get(name, 0) + int(size)

            url = _parse_next_link(headers.get("link"))

        return True

    # 1) Try authenticated mode first (better accuracy).
    ok = _collect(use_token=True)

    # 2) If authenticated repo listing failed, retry without token to avoid empty card.
    if TOKEN and not ok:
        _collect(use_token=False)

    # Prefer detailed totals when available; otherwise fallback to primary-language counts.
    if detailed_totals:
        return detailed_totals
    return primary_totals


def build_svg(username: str, lang_totals: dict[str, int], top_n: int = 6) -> str:
    width = 495
    height = 250
    title = f"{username}'s Top Languages"

    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)
    top_langs = sorted_langs[:top_n]
    total_bytes = sum(v for _, v in top_langs) or 1

    if not top_langs:
        top_langs = [("N/A", 1)]
        total_bytes = 1

    colors = ["#58A6FF", "#C792EA", "#31C6B8", "#F59E0B", "#EC4899", "#7C3AED"]

    rows_svg: list[str] = []
    bars_svg: list[str] = []

    base_y = 74
    row_h = 28
    bar_x = 40
    bar_w = 220
    pct_x = bar_x + bar_w + 16

    for idx, (lang, size) in enumerate(top_langs):
        y = base_y + idx * row_h
        pct = size * 100 / total_bytes
        color = colors[idx % len(colors)]

        rows_svg.append(
            f'''
  <circle cx="26" cy="{y - 5}" r="5" fill="{color}"/>
  <text x="40" y="{y}" class="label">{_svg_escape(lang)}</text>
    <text x="{pct_x}" y="{y + 10}" class="value" dominant-baseline="middle">{pct:.1f}%</text>
'''
        )

        bar_width = max(2, int(bar_w * pct / 100))
        bar_y = y + 7
        bars_svg.append(
            f'''
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="6" rx="3" fill="#1F2937"/>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="6" rx="3" fill="{color}"/>
'''
        )

    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{_svg_escape(title)}</title>
  <desc id="desc">Auto-generated GitHub top languages card.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0D1117"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <style>
      .title {{ fill: #58A6FF; font: 700 33px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .label {{ fill: #D1D5DB; font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .value {{ fill: #31C6B8; font: 700 16px 'Segoe UI', Ubuntu, Sans-Serif; }}
      .meta {{ fill: #6E7681; font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    </style>
  </defs>

  <rect x="1" y="1" width="493" height="248" rx="12" fill="url(#bg)" stroke="#30363D"/>
    <text x="24" y="42" class="title">{_svg_escape(title)}</text>

  {''.join(rows_svg)}
  {''.join(bars_svg)}

  <text x="24" y="238" class="meta">Updated: {_svg_escape(updated)}</text>
</svg>
'''


def main() -> None:
    if not USERNAME:
        raise SystemExit("USERNAME is required")

    try:
        totals = _fetch_repo_languages(USERNAME)
    except ApiError as e:
        print(f"Fetch languages failed, fallback to placeholder card: {e}")
        totals = {}

    svg = build_svg(USERNAME, totals)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {OUTPUT}")
    print(json.dumps({"language_count": len(totals), "languages": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
