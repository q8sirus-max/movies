#!/usr/bin/env python3
import base64
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import quote_plus
import webbrowser

from PIL import Image, ImageTk
import requests

from movie_search import TMDB_IMG, movie_details, search_movies, tmdb_request

CACHE_FILE = Path.home() / ".movieis_cache.json"
WATCHLIST_FILE = Path.home() / ".movieis_watchlist.json"
REPORTS_DIR = Path.cwd() / "movie_reports"
TMDB_BASE = "https://api.themoviedb.org/3"


def load_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_file(path: Path, data) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def format_money(amount) -> str:
    if not amount or not isinstance(amount, (int, float)) or amount <= 0:
        return "N/A"
    return f"${amount:,.0f}"


def _smart_search(query: str, api_key: str, year=None, language: str = "ar-SA"):
    langs = [language] if language == "en-US" else [language, "en-US"]
    candidates = [query.strip()]

    deduped = []
    for ch in query.strip():
        if not deduped or deduped[-1].lower() != ch.lower():
            deduped.append(ch)
    dedup_str = "".join(deduped)
    if dedup_str.lower() != query.strip().lower():
        candidates.append(dedup_str)

    for cand in candidates:
        for lang in langs:
            res = search_movies(cand, api_key, year=year, language=lang) or []
            if res:
                return res, cand, lang
    return [], query.strip(), language


def deep_movie_dossier(
    movie_id: int, api_key: str, cache: dict, language: str = "ar-SA", region: str = "KW"
) -> dict:
    cache_key = f"dossier_{language}_{region}_{movie_id}"
    if cache_key in cache:
        return cache[cache_key]

    details = movie_details(movie_id, api_key, language=language) or {}

    for section in ("similar", "recommendations", "keywords", "watch/providers", "videos"):
        params = {}
        if section in ("similar", "recommendations", "videos"):
            params["language"] = language
        try:
            resp = tmdb_request(f"/movie/{movie_id}/{section}", api_key, params, timeout=15)
            if resp.ok:
                key_name = "watch_providers" if section == "watch/providers" else section
                details[key_name] = resp.json()
        except requests.RequestException:
            pass

    # جلب الفيديوهات بالإنجليزية كاحتياط إذا كانت فارغة باللغة المختارة
    if not ((details.get("videos") or {}).get("results")) and language != "en-US":
        try:
            resp_en = tmdb_request(
                f"/movie/{movie_id}/videos", api_key, {"language": "en-US"}, timeout=15
            )
            if resp_en.ok:
                details["videos"] = resp_en.json()
        except requests.RequestException:
            pass

    cache[cache_key] = details
    save_json_file(CACHE_FILE, cache)
    return details


class MovieisDeepApp:
    def __init__(self, root: tk.Tk, api_key: str):
        self.root = root
        self.api_key = api_key
        self.results = []
        self.current_dossier = None
        self.current_watch_url = None
        self.current_trailer_url = None
        self.poster_img = None
        self.queue = queue.Queue()
        self.selection_seq = 0

        self.cache = load_json_file(CACHE_FILE, {})
        self.watchlist = load_json_file(WATCHLIST_FILE, {})

        self._build_ui()
        self.root.after(50, self._poll_queue)

    def _poll_queue(self):
        while True:
            try:
                callback = self.queue.get_nowait()
            except queue.Empty:
                break
            callback()
        self.root.after(50, self._poll_queue)

    def _build_ui(self):
        self.root.title("Movieis — Deep Movie & Watch Finder")
        self.root.geometry("1220x780")
        self.root.minsize(980, 640)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Movie:").pack(side="left")
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(top, textvariable=self.query_var, width=28)
        self.query_entry.pack(side="left", padx=(6, 8))
        self.query_entry.bind("<Return>", lambda e: self.on_search())

        ttk.Label(top, text="Year:").pack(side="left")
        self.year_var = tk.StringVar()
        year_entry = ttk.Entry(top, textvariable=self.year_var, width=6)
        year_entry.pack(side="left", padx=(6, 8))
        year_entry.bind("<Return>", lambda e: self.on_search())

        ttk.Label(top, text="Region:").pack(side="left")
        self.region_var = tk.StringVar(value="KW")
        region_combo = ttk.Combobox(
            top,
            textvariable=self.region_var,
            values=("KW", "SA", "AE", "EG", "US", "GB"),
            width=5,
            state="readonly",
        )
        region_combo.pack(side="left", padx=(6, 8))

        ttk.Label(top, text="Lang:").pack(side="left")
        self.lang_var = tk.StringVar(value="ar-SA")
        lang_combo = ttk.Combobox(
            top,
            textvariable=self.lang_var,
            values=("ar-SA", "en-US"),
            width=7,
            state="readonly",
        )
        lang_combo.pack(side="left", padx=(6, 10))

        self.autoplay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Auto-play", variable=self.autoplay_var).pack(
            side="left", padx=(0, 8)
        )

        self.search_btn = ttk.Button(top, text="Deep Search", command=self.on_search)
        self.search_btn.pack(side="left", padx=(0, 5))

        self.watch_btn = ttk.Button(
            top, text="Open Watch Page", command=self.on_open_watch_page, state="disabled"
        )
        self.watch_btn.pack(side="left", padx=(0, 5))

        self.trailer_btn = ttk.Button(
            top, text="Watch Trailer", command=self.on_open_trailer, state="disabled"
        )
        self.trailer_btn.pack(side="left", padx=(0, 5))

        self.save_btn = ttk.Button(
            top, text="Save", command=self.on_save_watchlist, state="disabled"
        )
        self.save_btn.pack(side="left", padx=(0, 5))

        self.export_btn = ttk.Button(
            top, text="Export MD", command=self.on_export_report, state="disabled"
        )
        self.export_btn.pack(side="left", padx=(0, 5))

        self.watchlist_btn = ttk.Button(
            top, text=f"Watchlist ({len(self.watchlist)})", command=self.on_show_watchlist
        )
        self.watchlist_btn.pack(side="right")

        self.status = tk.StringVar(value="Ready — Enter a movie title for deep search.")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(10, 4)).pack(
            fill="x", side="bottom"
        )

        paned = ttk.Panedwindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        cols = ("title", "year", "rating")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("title", text="Title")
        self.tree.heading("year", text="Year")
        self.tree.heading("rating", text="Rating")
        self.tree.column("title", width=290, anchor="w")
        self.tree.column("year", width=65, anchor="center")
        self.tree.column("rating", width=65, anchor="center")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        header_box = ttk.Frame(right)
        header_box.pack(fill="x", pady=(0, 8))

        self.poster_label = ttk.Label(header_box)
        self.poster_label.pack(side="left", anchor="n", padx=(0, 14))

        header_info = ttk.Frame(header_box)
        header_info.pack(side="left", fill="both", expand=True)

        self.title_label = ttk.Label(
            header_info,
            text="Search for a movie to begin",
            font=("Segoe UI", 15, "bold"),
            wraplength=640,
            justify="left",
        )
        self.title_label.pack(anchor="w")

        self.tagline_label = ttk.Label(
            header_info,
            text="",
            font=("Segoe UI", 10, "italic"),
            wraplength=640,
            justify="left",
        )
        self.tagline_label.pack(anchor="w", pady=(2, 6))

        self.meta_label = ttk.Label(header_info, text="", justify="left", wraplength=640)
        self.meta_label.pack(anchor="w")

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        # تبويب البحث العميق عن المشاهدة والمنصات المجانية
        tab_watch = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab_watch, text="Deep Watch & Free Search")

        quick_bar = ttk.Frame(tab_watch)
        quick_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(quick_bar, text="Quick Free Platform Search:").pack(side="left", padx=(0, 6))
        self.yt_btn = ttk.Button(
            quick_bar, text="Search YouTube", command=lambda: self._open_platform_search("youtube"), state="disabled"
        )
        self.yt_btn.pack(side="left", padx=(0, 6))
        self.tubi_btn = ttk.Button(
            quick_bar, text="Search Tubi", command=lambda: self._open_platform_search("tubi"), state="disabled"
        )
        self.tubi_btn.pack(side="left", padx=(0, 6))
        self.pluto_btn = ttk.Button(
            quick_bar, text="Search Pluto TV", command=lambda: self._open_platform_search("pluto"), state="disabled"
        )
        self.pluto_btn.pack(side="left", padx=(0, 6))

        self.watch_text = tk.Text(tab_watch, wrap="word", relief="flat", padx=6, pady=6)
        self.watch_text.configure(state="disabled")
        self.watch_text.pack(fill="both", expand=True)

        tab_overview = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab_overview, text="Overview & Cast")

        ttk.Label(tab_overview, text="Synopsis:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.overview_text = tk.Text(tab_overview, wrap="word", height=7, relief="flat", padx=4, pady=4)
        self.overview_text.configure(state="disabled")
        self.overview_text.pack(fill="x", pady=(2, 8))

        ttk.Label(tab_overview, text="Key Crew & Top Cast:", font=("Segoe UI", 10, "bold")).pack(
            anchor="w"
        )
        self.cast_text = tk.Text(tab_overview, wrap="word", height=10, relief="flat", padx=4, pady=4)
        self.cast_text.configure(state="disabled")
        self.cast_text.pack(fill="both", expand=True, pady=(2, 0))

        tab_related = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab_related, text="Similar & Recommendations")

        ttk.Label(
            tab_related,
            text="Double-click any related movie to open it directly:",
            font=("Segoe UI", 9, "italic"),
        ).pack(anchor="w", pady=(0, 6))

        rel_cols = ("relation", "title", "year", "rating")
        self.rel_tree = ttk.Treeview(
            tab_related, columns=rel_cols, show="headings", selectmode="browse"
        )
        self.rel_tree.heading("relation", text="Type")
        self.rel_tree.heading("title", text="Title")
        self.rel_tree.heading("year", text="Year")
        self.rel_tree.heading("rating", text="Rating")
        self.rel_tree.column("relation", width=130, anchor="w")
        self.rel_tree.column("title", width=360, anchor="w")
        self.rel_tree.column("year", width=70, anchor="center")
        self.rel_tree.column("rating", width=70, anchor="center")
        self.rel_tree.pack(fill="both", expand=True)
        self.rel_tree.bind("<Double-1>", self.on_open_related)

        tab_deep = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab_deep, text="Finance & Keywords")

        self.deep_text = tk.Text(tab_deep, wrap="word", relief="flat", padx=6, pady=6)
        self.deep_text.configure(state="disabled")
        self.deep_text.pack(fill="both", expand=True)

        self.query_entry.focus_set()

    def set_status(self, text: str):
        self.status.set(text)

    def on_search(self):
        query = self.query_var.get().strip()
        if not query:
            messagebox.showinfo("Movieis", "Type a movie name first.")
            return

        year = None
        raw_year = self.year_var.get().strip()
        if raw_year:
            if not raw_year.isdigit():
                messagebox.showwarning("Movieis", "Year must be a number.")
                return
            year = int(raw_year)

        lang = self.lang_var.get() or "ar-SA"
        self.search_btn.configure(state="disabled")
        self.set_status(f"Deep searching for '{query}'...")
        threading.Thread(
            target=self._search_worker, args=(query, year, lang), daemon=True
        ).start()

    def _search_worker(self, query: str, year, language: str):
        try:
            results, used_query, used_lang = _smart_search(
                query, self.api_key, year=year, language=language
            )
        except Exception as exc:
            self.queue.put(lambda: self._search_failed(exc))
            return
        self.queue.put(lambda: self._show_results(results, used_query, used_lang))

    def _search_failed(self, exc: Exception):
        self.search_btn.configure(state="normal")
        self.set_status(f"Search error: {exc}")
        messagebox.showerror("Movieis", f"Search failed:\n{exc}")

    def _show_results(self, results: list, used_query: str = "", used_lang: str = ""):
        self.search_btn.configure(state="normal")
        self.results = results
        self.tree.delete(*self.tree.get_children())
        self._reset_details()

        if not results:
            self.set_status("No results found from TMDb.")
            return

        for i, m in enumerate(results):
            title = m.get("title") or m.get("original_title") or "?"
            year = (m.get("release_date") or "")[:4] or "----"
            rating = float(m.get("vote_average") or 0)
            self.tree.insert(
                "", "end", iid=str(i), values=(title, year, f"{rating:.1f}" if rating else "N/A")
            )

        note = f" (matched '{used_query}' in {used_lang})" if used_query and used_lang else ""
        self.set_status(f"Found {len(results)} result(s){note}. Select one for deep watch details.")
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])

    def _set_text_widget(self, widget: tk.Text, content: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _reset_details(self):
        self.current_dossier = None
        self.current_watch_url = None
        self.current_trailer_url = None
        self.watch_btn.configure(state="disabled")
        self.trailer_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.yt_btn.configure(state="disabled")
        self.tubi_btn.configure(state="disabled")
        self.pluto_btn.configure(state="disabled")
        self.title_label.configure(text="Search for a movie to begin")
        self.tagline_label.configure(text="")
        self.meta_label.configure(text="")
        self.poster_label.configure(image="")
        self.poster_img = None
        self._set_text_widget(self.watch_text, "")
        self._set_text_widget(self.overview_text, "")
        self._set_text_widget(self.cast_text, "")
        self._set_text_widget(self.deep_text, "")
        self.rel_tree.delete(*self.rel_tree.get_children())

    def on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.results):
            return
        movie = self.results[idx]
        self._start_deep_load(
            movie["id"], movie.get("title") or movie.get("original_title") or "Movie"
        )

    def _start_deep_load(self, movie_id: int, label_title: str):
        self.selection_seq += 1
        seq = self.selection_seq
        lang = self.lang_var.get() or "ar-SA"
        region = self.region_var.get() or "KW"
        self.set_status(f"Running deep research for '{label_title}' ({region})...")
        threading.Thread(
            target=self._details_worker, args=(movie_id, seq, lang, region), daemon=True
        ).start()

    def _details_worker(self, movie_id: int, seq: int, language: str, region: str):
        try:
            dossier = deep_movie_dossier(
                movie_id, self.api_key, self.cache, language=language, region=region
            )
        except Exception as exc:
            if seq == self.selection_seq:
                self.queue.put(lambda: self.set_status(f"Failed to load details: {exc}"))
            return

        poster_bytes = None
        poster_path = dossier.get("poster_path")
        if poster_path:
            poster_cache_key = f"poster_{hashlib.md5(poster_path.encode()).hexdigest()}"
            if poster_cache_key in self.cache:
                try:
                    poster_bytes = base64.b64decode(self.cache[poster_cache_key])
                except Exception:
                    poster_bytes = None
            if poster_bytes is None:
                try:
                    resp = requests.get(f"{TMDB_IMG}{poster_path}", timeout=20)
                    if resp.ok:
                        poster_bytes = resp.content
                        self.cache[poster_cache_key] = base64.b64encode(poster_bytes).decode("ascii")
                        save_json_file(CACHE_FILE, self.cache)
                except requests.RequestException:
                    poster_bytes = None

        if seq == self.selection_seq:
            self.queue.put(lambda: self._show_dossier(dossier, poster_bytes, region))

    def _show_dossier(self, m: dict, poster_bytes, region: str):
        self.current_dossier = m
        self.save_btn.configure(state="normal")
        self.export_btn.configure(state="normal")
        self.yt_btn.configure(state="normal")
        self.tubi_btn.configure(state="normal")
        self.pluto_btn.configure(state="normal")

        title = m.get("title") or m.get("original_title") or "?"
        original = m.get("original_title") or ""
        heading = f"{title} ({original})" if original and original != title else title
        self.title_label.configure(text=heading)
        self.tagline_label.configure(text=f"“{m['tagline']}”" if m.get("tagline") else "")

        rating = float(m.get("vote_average") or 0)
        genres = ", ".join(g["name"] for g in m.get("genres", [])) or "N/A"
        countries = ", ".join(c["name"] for c in m.get("production_countries", [])) or "N/A"
        rel_date = m.get("release_date") or "N/A"
        runtime = m.get("runtime") or "N/A"
        status_str = m.get("status") or "N/A"
        votes = int(m.get("vote_count") or 0)
        pop = float(m.get("popularity") or 0)

        meta_lines = [
            f"Release: {rel_date}   |   Runtime: {runtime} min   |   Status: {status_str}",
            f"Rating: {rating:.1f}/10 ({votes:,} votes)   |   Popularity: {pop:.1f}",
            f"Genres: {genres}",
            f"Countries: {countries}",
        ]
        if m.get("homepage"):
            meta_lines.append(f"Homepage: {m['homepage']}")
        self.meta_label.configure(text="\n".join(meta_lines))

        # استخراج الإعلانات والفيديوهات الرسمية
        videos = (m.get("videos") or {}).get("results") or []
        yt_videos = [
            v for v in videos if (v.get("site") or "").lower() == "youtube" and v.get("key")
        ]
        trailer = next(
            (v for v in yt_videos if (v.get("type") or "").lower() == "trailer"),
            yt_videos[0] if yt_videos else None,
        )
        if trailer:
            self.current_trailer_url = f"https://www.youtube.com/watch?v={trailer['key']}"
            self.trailer_btn.configure(state="normal")
            if self.autoplay_var.get():
                webbrowser.open(self.current_trailer_url)
                self.set_status(f"Auto-playing trailer: {self.current_trailer_url}")

        # البحث العميق عن منصات المشاهدة والمجانية
        providers_by_region = (m.get("watch_providers") or {}).get("results") or {}
        reg_data = providers_by_region.get(region) or providers_by_region.get("US") or {}
        used_region = (
            region if region in providers_by_region else ("US" if "US" in providers_by_region else None)
        )

        watch_lines = []
        if used_region:
            if used_region != region:
                watch_lines.append(
                    f"No direct providers in '{region}', showing fallback '{used_region}':\n"
                )
            else:
                watch_lines.append(f"Availability in Region: {used_region}\n")

            for label, field in (
                ("Free (مجاني)", "free"),
                ("Free with Ads (مجاني بإعلانات)", "ads"),
                ("Subscription / Stream", "flatrate"),
                ("Rent", "rent"),
                ("Buy", "buy"),
            ):
                p_list = reg_data.get(field) or []
                names = [p.get("provider_name") for p in p_list if p.get("provider_name")]
                watch_lines.append(f"• {label}: {', '.join(names) if names else 'Not listed'}")

            link = reg_data.get("link") or (
                f"https://www.themoviedb.org/movie/{m.get('id')}/watch" if m.get("id") else None
            )
            if link:
                self.current_watch_url = link
                self.watch_btn.configure(state="normal")
                watch_lines.append(f"\nTMDb Watch Directory: {link}")
        else:
            self.current_watch_url = (
                f"https://www.themoviedb.org/movie/{m.get('id')}/watch" if m.get("id") else None
            )
            if self.current_watch_url:
                self.watch_btn.configure(state="normal")
            watch_lines.append(
                f"No streaming/free/rent/buy providers listed for '{region}' on TMDb."
            )
            if self.current_watch_url:
                watch_lines.append(f"Check TMDb Watch Page: {self.current_watch_url}")

        if yt_videos:
            watch_lines.append("\nOfficial Videos / Trailers:")
            for v in yt_videos[:5]:
                v_url = f"https://www.youtube.com/watch?v={v['key']}"
                watch_lines.append(f"  - [{v.get('type') or 'Video'}] {v.get('name') or 'Clip'}: {v_url}")

        self._set_text_widget(self.watch_text, "\n".join(watch_lines))

        # القصة والطاقم
        self._set_text_widget(self.overview_text, (m.get("overview") or "No overview available.").strip())

        credits = m.get("credits") or {}
        directors = [
            p.get("name") for p in credits.get("crew", []) if p.get("job") == "Director"
        ]
        writers = [
            p.get("name")
            for p in credits.get("crew", [])
            if p.get("department") == "Writing"
        ][:4]
        cast = credits.get("cast", [])[:12]

        cast_sections = []
        if directors:
            cast_sections.append("Director(s): " + ", ".join(directors))
        if writers:
            cast_sections.append("Writers: " + ", ".join(writers))
        if cast:
            cast_sections.append("\nTop Cast:")
            for c in cast:
                cast_sections.append(f"  • {c.get('name')} — as {c.get('character') or 'N/A'}")
        self._set_text_widget(
            self.cast_text, "\n".join(cast_sections) if cast_sections else "No credits data available."
        )

        # أفلام مشابهة وتوصيات
        self.rel_tree.delete(*self.rel_tree.get_children())
        seen_ids = {m.get("id")}
        related_entries = []

        for rel_type, key in (("Recommendation", "recommendations"), ("Similar", "similar")):
            items = (m.get(key) or {}).get("results", [])[:8]
            for item in items:
                rid = item.get("id")
                if not rid or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                r_title = item.get("title") or item.get("original_title") or "?"
                r_year = (item.get("release_date") or "")[:4] or "----"
                r_rating = float(item.get("vote_average") or 0)
                related_entries.append(
                    (rid, r_title, rel_type, r_year, f"{r_rating:.1f}" if r_rating else "N/A")
                )

        for rid, r_title, rel_type, r_year, r_rating in related_entries:
            self.rel_tree.insert("", "end", iid=str(rid), values=(rel_type, r_title, r_year, r_rating))

        # المؤشرات المالية والكلمات المفتاحية
        budget = m.get("budget") or 0
        revenue = m.get("revenue") or 0
        roi_line = "ROI: N/A"
        if budget > 0 and revenue > 0:
            roi_pct = ((revenue - budget) / budget) * 100
            roi_line = f"ROI: {roi_pct:+.1f}% (Multiple: {revenue / budget:.2f}x)"

        companies = [c.get("name") for c in m.get("production_companies", [])]
        languages = [l.get("english_name") or l.get("name") for l in m.get("spoken_languages", [])]
        keywords = [k.get("name") for k in (m.get("keywords") or {}).get("keywords", [])]

        finance_lines = [
            f"Budget: {format_money(budget)}",
            f"Box Office Revenue: {format_money(revenue)}",
            roi_line,
            f"Original Language: {m.get('original_language') or 'N/A'}",
            f"Spoken Languages: {', '.join(languages) or 'N/A'}",
            f"Production Companies: {', '.join(companies) or 'N/A'}",
            f"\nKeywords ({len(keywords)}): {', '.join(keywords) if keywords else 'N/A'}",
        ]
        self._set_text_widget(self.deep_text, "\n".join(finance_lines))

        if poster_bytes:
            try:
                img = Image.open(io.BytesIO(poster_bytes))
                img.thumbnail((190, 285))
                self.poster_img = ImageTk.PhotoImage(img)
                self.poster_label.configure(image=self.poster_img)
            except Exception:
                self.poster_label.configure(image="")
                self.poster_img = None
        else:
            self.poster_label.configure(image="")
            self.poster_img = None

        self.set_status(f"Deep dossier ready for '{title}'.")

    def _get_search_phrase(self) -> str:
        m = self.current_dossier or {}
        base = m.get("original_title") or m.get("title") or self.query_var.get().strip()
        year = (m.get("release_date") or "")[:4]
        return f"{base} {year}".strip() if year else base

    def _open_platform_search(self, platform: str):
        phrase = self._get_search_phrase()
        if not phrase:
            return
        q = quote_plus(f"{phrase} full movie")
        urls = {
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "tubi": f"https://tubitv.com/search/{quote_plus(phrase)}",
            "pluto": f"https://pluto.tv/en/search?q={quote_plus(phrase)}",
        }
        url = urls.get(platform)
        if url:
            webbrowser.open(url)
            self.set_status(f"Opened {platform} search for '{phrase}'.")

    def on_open_watch_page(self):
        if self.current_watch_url:
            webbrowser.open(self.current_watch_url)
            self.set_status(f"Opened watch page: {self.current_watch_url}")

    def on_open_trailer(self):
        if self.current_trailer_url:
            webbrowser.open(self.current_trailer_url)
            self.set_status(f"Opened trailer: {self.current_trailer_url}")

    def on_open_related(self, _event=None):
        sel = self.rel_tree.selection()
        if not sel:
            return
        rel_id = int(sel[0])
        vals = self.rel_tree.item(sel[0], "values")
        rel_title = vals[1] if len(vals) > 1 else f"Movie #{rel_id}"
        self._start_deep_load(rel_id, rel_title)

    def on_save_watchlist(self):
        if not self.current_dossier:
            return
        m = self.current_dossier
        mid = str(m.get("id"))
        self.watchlist[mid] = {
            "id": m.get("id"),
            "title": m.get("title") or m.get("original_title"),
            "year": (m.get("release_date") or "")[:4],
            "rating": m.get("vote_average"),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        save_json_file(WATCHLIST_FILE, self.watchlist)
        self.watchlist_btn.configure(text=f"Watchlist ({len(self.watchlist)})")
        self.set_status(f"Saved '{self.watchlist[mid]['title']}' to Watchlist.")

    def on_show_watchlist(self):
        if not self.watchlist:
            messagebox.showinfo("Watchlist", "Your watchlist is currently empty.")
            return
        win = tk.Toplevel(self.root)
        win.title("Saved Watchlist")
        win.geometry("540x360")

        tree = ttk.Treeview(win, columns=("title", "year", "rating"), show="headings")
        tree.heading("title", text="Title")
        tree.heading("year", text="Year")
        tree.heading("rating", text="Rating")
        tree.column("title", width=330)
        tree.column("year", width=80, anchor="center")
        tree.column("rating", width=80, anchor="center")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        for mid, item in self.watchlist.items():
            r = float(item.get("rating") or 0)
            tree.insert(
                "",
                "end",
                iid=str(mid),
                values=(item.get("title"), item.get("year") or "----", f"{r:.1f}" if r else "N/A"),
            )

        def open_selected(_e=None):
            s = tree.selection()
            if s:
                movie_id = int(s[0])
                title = self.watchlist[str(movie_id)].get("title", "Movie")
                win.destroy()
                self._start_deep_load(movie_id, title)

        tree.bind("<Double-1>", open_selected)

    def on_export_report(self):
        if not self.current_dossier:
            return
        m = self.current_dossier
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        title = m.get("title") or m.get("original_title") or "movie"
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title).strip()
        md_path = REPORTS_DIR / f"{safe_name}_{m.get('id')}.md"

        directors = [
            p.get("name")
            for p in (m.get("credits") or {}).get("crew", [])
            if p.get("job") == "Director"
        ]
        cast = (m.get("credits") or {}).get("cast", [])[:10]
        genres = ", ".join(g["name"] for g in m.get("genres", [])) or "N/A"
        keywords = ", ".join(k.get("name") for k in (m.get("keywords") or {}).get("keywords", [])) or "N/A"

        lines = [
            f"# {title}",
            "",
            f"- **Release Date:** {m.get('release_date') or 'N/A'}",
            f"- **Runtime:** {m.get('runtime') or 'N/A'} min",
            f"- **Rating:** {float(m.get('vote_average') or 0):.1f}/10 ({m.get('vote_count', 0)} votes)",
            f"- **Genres:** {genres}",
            f"- **Director(s):** {', '.join(directors) or 'N/A'}",
            f"- **Budget:** {format_money(m.get('budget'))}",
            f"- **Revenue:** {format_money(m.get('revenue'))}",
            "",
            "## Synopsis",
            (m.get("overview") or "No overview available.").strip(),
            "",
            "## Top Cast",
        ]
        for c in cast:
            lines.append(f"- **{c.get('name')}** as *{c.get('character') or 'N/A'}*")
        lines.extend(["", "## Keywords", keywords, ""])

        md_path.write_text("\n".join(lines), encoding="utf-8")
        messagebox.showinfo("Export Complete", f"Report saved to:\n{md_path}")
        self.set_status(f"Exported report: {md_path.name}")


def resolve_api_key() -> str:
    key = os.environ.get("TMDB_API_KEY")
    if key:
        return key.strip()
    root = tk.Tk()
    root.withdraw()
    key = simpledialog.askstring(
        "Movieis - TMDB key",
        "Enter your TMDB API key or Read Access Token:",
        show="*",
    )
    root.destroy()
    if not key:
        sys.exit("No API key provided.")
    return key.strip()


def main():
    api_key = resolve_api_key()
    root = tk.Tk()
    MovieisDeepApp(root, api_key)
    root.mainloop()


if __name__ == "__main__":
    main()