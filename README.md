# Movieis

Movieis is a desktop command-line application that lets users search for movies and view details such as ratings, cast, release dates, genres, and posters. It uses the TMDB API to fetch and display movie metadata.

## Features

- Search for any movie by name
- Filter results by release year
- View ratings, vote counts, and short overviews for every match
- Show full details for a chosen result: runtime, status, genres, countries, tagline, homepage, poster, and top cast
- Play the official trailer in your browser
- Show legal streaming / rent / buy availability (via TMDB watch providers)
- Output raw JSON for scripting
- Localized results (defaults to `ar-SA`)
- Accepts both a v3 API key and a v4 read access token; if a v4 token is rejected, its embedded v3 key is used automatically

## Requirements

- Python 3.8+
- A free TMDB API key or Read Access Token: https://www.themoviedb.org/settings/api

The graphical interface also needs Tkinter (bundled with Python) and Pillow.

## Install

```bash
pip install -r requirements.txt
```

## Configure

Set your TMDB API key as an environment variable.

Windows (cmd):

```cmd
set TMDB_API_KEY=your_key
```

Linux / macOS:

```bash
export TMDB_API_KEY=your_key
```

Alternatively, pass it per command with `--api-key`.

## Usage

### Graphical interface

```bash
python movieis_gui.py
```

A desktop window with a search bar, a results table, and a deep-research panel showing the poster, rating, runtime, genres, overview, top cast, trailer, and where to watch. Pick a region and click **Watch Trailer** or **Open Watch Page**.

### Command line

```bash
python movie_search.py "Inception"
python movie_search.py "Inception" --year 2010
python movie_search.py "Inception" --pick 1
python movie_search.py "Inception" --play
python movie_search.py "Inception" --watch --region US
python movie_search.py "Inception" --all
python movie_search.py "Inception" --json
```

### Options

| Option | Description |
| --- | --- |
| `query` | Movie name to search for (required) |
| `--year` | Filter by release year |
| `--lang` | Language for results (default: `ar-SA`) |
| `--api-key` | TMDB API key or read access token (or set `TMDB_API_KEY`) |
| `--pick N` | Show details for result number N |
| `--play` | Open the official trailer for the top result |
| `--watch` | Show legal streaming / rent / buy availability |
| `--region` | Region for watch providers (default: `KW`) |
| `--all` | Show details for every result |
| `--json` | Print raw JSON results |

## License

MIT
