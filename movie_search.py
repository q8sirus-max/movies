#!/usr/bin/env python3
import argparse
import json
import os
import sys

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"


def get_api_key(cli_key):
    key = cli_key or os.environ.get("TMDB_API_KEY")
    if not key:
        sys.exit(
            "Missing TMDB API key.\n"
            "Set it with:  set TMDB_API_KEY=your_key   (Windows)\n"
            "          or: export TMDB_API_KEY=your_key (Linux/macOS)\n"
            "Accepts either the v3 API key or the v4 read access token.\n"
            "Get one at https://www.themoviedb.org/settings/api"
        )
    return key


def tmdb_get(path, api_key, params=None):
    params = dict(params or {})
    headers = {}
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    resp = requests.get(f"{TMDB_API}{path}", params=params, headers=headers, timeout=20)
    if resp.status_code == 401:
        sys.exit("TMDB rejected the token (401). Check your API key / read access token.")
    resp.raise_for_status()
    return resp.json()


def search_movies(query, api_key, year=None, language="ar-SA"):
    params = {"query": query, "language": language, "include_adult": "false"}
    if year:
        params["year"] = year
    return tmdb_get("/search/movie", api_key, params).get("results", [])


def movie_details(movie_id, api_key, language="ar-SA"):
    return tmdb_get(
        f"/movie/{movie_id}",
        api_key,
        {"language": language, "append_to_response": "credits,release_dates"},
    )


def fmt_rating(value):
    return f"{value:.1f}" if isinstance(value, (int, float)) and value else "N/A"


def print_results(results):
    if not results:
        print("No results found.")
        return
    print(f"\nFound {len(results)} result(s):\n")
    for i, m in enumerate(results, 1):
        title = m.get("title") or m.get("original_title") or "?"
        year = (m.get("release_date") or "")[:4] or "----"
        print(f"[{i}] {title} ({year})  ★ {fmt_rating(m.get('vote_average'))}")
        overview = (m.get("overview") or "").strip()
        if overview:
            print(f"     {overview[:160]}{'...' if len(overview) > 160 else ''}")
        print()


def print_details(m, api_key):
    title = m.get("title") or m.get("original_title") or "?"
    print("\n" + "=" * 60)
    print(f"{title} ({m.get('original_title', '')})".strip())
    print("=" * 60)
    print(f"Release date : {m.get('release_date') or 'N/A'}")
    print(f"Rating       : ★ {fmt_rating(m.get('vote_average'))} ({m.get('vote_count', 0)} votes)")
    print(f"Runtime      : {m.get('runtime') or 'N/A'} min")
    print(f"Status       : {m.get('status') or 'N/A'}")
    genres = ", ".join(g["name"] for g in m.get("genres", [])) or "N/A"
    print(f"Genres       : {genres}")
    countries = ", ".join(c["name"] for c in m.get("production_countries", [])) or "N/A"
    print(f"Countries    : {countries}")
    print(f"Tagline      : {m.get('tagline') or 'N/A'}")
    if m.get("homepage"):
        print(f"Homepage     : {m['homepage']}")
    if m.get("poster_path"):
        print(f"Poster       : {TMDB_IMG}{m['poster_path']}")
    overview = (m.get("overview") or "").strip()
    if overview:
        print(f"\nOverview:\n{overview}")
    cast = (m.get("credits") or {}).get("cast", [])[:8]
    if cast:
        print("\nTop cast:")
        for c in cast:
            print(f"  - {c.get('name')} as {c.get('character') or '?'}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Search for a movie across TMDB.")
    parser.add_argument("query", nargs="+", help="Movie name to search for")
    parser.add_argument("--year", type=int, help="Filter by release year")
    parser.add_argument("--lang", default="ar-SA", help="Language for results (default: ar-SA)")
    parser.add_argument("--api-key", help="TMDB API key (or set TMDB_API_KEY)")
    parser.add_argument("--pick", type=int, help="Show details for result number N")
    parser.add_argument("--all", action="store_true", help="Show details for every result")
    parser.add_argument("--json", action="store_true", help="Print raw JSON results")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    query = " ".join(args.query)

    results = search_movies(query, api_key, year=args.year, language=args.lang)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print_results(results)

    if args.pick:
        if 1 <= args.pick <= len(results):
            print_details(movie_details(results[args.pick - 1]["id"], api_key, args.lang), api_key)
        else:
            print(f"Pick must be between 1 and {len(results)}.")
    elif args.all:
        for m in results:
            print_details(movie_details(m["id"], api_key, args.lang), api_key)


if __name__ == "__main__":
    main()
