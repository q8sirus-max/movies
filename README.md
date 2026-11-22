# Movieis

Movieis is a desktop command-line application that lets users search for movies and view details such as ratings, cast, release dates, genres, and posters. It uses the TMDB API to fetch and display movie metadata.

## Features

- Search for any movie by name
- Filter results by release year
- View ratings, vote counts, and short overviews for every match
- Show full details for a chosen result: runtime, status, genres, countries, tagline, homepage, poster, and top cast
- Output raw JSON for scripting
- Localized results (defaults to `ar-SA`)

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

A desktop window with a search bar, a results table, and a details panel showing the poster, rating, runtime, genres, overview, and top cast.

### Command line

```bash
python movie_search.py "Inception"
python movie_search.py "Inception" --year 2010
python movie_search.py "Inception" --pick 1
python movie_search.py "Inception" --all
python movie_search.py "Inception" --json
```

### Options

| Option | Description |
| --- | --- |
| `query` | Movie name to search for (required) |
| `--year` | Filter by release year |
| `--lang` | Language for results (default: `ar-SA`) |
| `--api-key` | TMDB API key (or set `TMDB_API_KEY`) |
| `--pick N` | Show details for result number N |
| `--all` | Show details for every result |
| `--json` | Print raw JSON results |

## License

MIT
