#!/usr/bin/env python3
import io
import os
import queue
import sys
import threading

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import requests
from PIL import Image, ImageTk

from movie_search import TMDB_IMG, movie_details, search_movies


class MovieisApp:
    def __init__(self, root, api_key):
        self.root = root
        self.api_key = api_key
        self.results = []
        self.poster_img = None
        self.queue = queue.Queue()
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
        self.root.title("Movieis")
        self.root.geometry("1000x660")
        self.root.minsize(840, 540)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Movie:").pack(side="left")
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(top, textvariable=self.query_var, width=42)
        self.query_entry.pack(side="left", padx=(6, 12))
        self.query_entry.bind("<Return>", lambda e: self.on_search())

        ttk.Label(top, text="Year:").pack(side="left")
        self.year_var = tk.StringVar()
        year_entry = ttk.Entry(top, textvariable=self.year_var, width=8)
        year_entry.pack(side="left", padx=(6, 12))
        year_entry.bind("<Return>", lambda e: self.on_search())

        self.search_btn = ttk.Button(top, text="Search", command=self.on_search)
        self.search_btn.pack(side="left")

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(10, 2)).pack(
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
        self.tree.column("title", width=300, anchor="w")
        self.tree.column("year", width=70, anchor="center")
        self.tree.column("rating", width=70, anchor="center")
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.poster_label = ttk.Label(right)
        self.poster_label.pack(side="left", anchor="n", padx=(0, 12), pady=4)

        info = ttk.Frame(right)
        info.pack(side="left", fill="both", expand=True)

        self.title_label = ttk.Label(info, text="Search for a movie", font=("Segoe UI", 14, "bold"),
                                     wraplength=520, justify="left")
        self.title_label.pack(anchor="w")

        self.meta_label = ttk.Label(info, text="", justify="left", wraplength=520)
        self.meta_label.pack(anchor="w", pady=(4, 8))

        self.overview = tk.Text(info, wrap="word", height=12, relief="flat", highlightthickness=0)
        self.overview.configure(state="disabled")
        self.overview.pack(fill="both", expand=True)

        self.cast_label = ttk.Label(info, text="", justify="left", wraplength=520)
        self.cast_label.pack(anchor="w", pady=(8, 0))

        self.query_entry.focus_set()

    def set_status(self, text):
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

        self.search_btn.configure(state="disabled")
        self.set_status(f"Searching for '{query}'...")
        threading.Thread(target=self._search_worker, args=(query, year), daemon=True).start()

    def _search_worker(self, query, year):
        try:
            results = search_movies(query, self.api_key, year=year)
        except Exception as exc:
            self.queue.put(lambda: self._search_failed(exc))
            return
        self.queue.put(lambda: self._show_results(results))

    def _search_failed(self, exc):
        self.search_btn.configure(state="normal")
        self.set_status("Search failed.")
        messagebox.showerror("Movieis", f"Search failed:\n{exc}")

    def _show_results(self, results):
        self.search_btn.configure(state="normal")
        self.results = results
        self.tree.delete(*self.tree.get_children())
        self._reset_details()
        if not results:
            self.set_status("No results found.")
            return
        for i, m in enumerate(results):
            title = m.get("title") or m.get("original_title") or "?"
            year = (m.get("release_date") or "")[:4] or "----"
            rating = m.get("vote_average") or 0
            self.tree.insert("", "end", iid=str(i), values=(title, year, f"{rating:.1f}" if rating else "N/A"))
        self.set_status(f"Found {len(results)} result(s). Select one for details.")
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])

    def _reset_details(self):
        self.title_label.configure(text="Search for a movie")
        self.meta_label.configure(text="")
        self.cast_label.configure(text="")
        self.poster_label.configure(image="")
        self.poster_img = None
        self.overview.configure(state="normal")
        self.overview.delete("1.0", "end")
        self.overview.configure(state="disabled")

    def on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.results):
            return
        movie = self.results[idx]
        self.set_status("Loading details...")
        threading.Thread(target=self._details_worker, args=(movie,), daemon=True).start()

    def _details_worker(self, movie):
        try:
            details = movie_details(movie["id"], self.api_key)
        except Exception as exc:
            self.queue.put(lambda: self.set_status(f"Details failed: {exc}"))
            return
        poster_bytes = None
        if details.get("poster_path"):
            try:
                resp = requests.get(f"{TMDB_IMG}{details['poster_path']}", timeout=20)
                if resp.ok:
                    poster_bytes = resp.content
            except requests.RequestException:
                poster_bytes = None
        self.queue.put(lambda: self._show_details(details, poster_bytes))

    def _show_details(self, m, poster_bytes):
        title = m.get("title") or m.get("original_title") or "?"
        original = m.get("original_title") or ""
        heading = f"{title} ({original})" if original and original != title else title
        self.title_label.configure(text=heading)

        rating = m.get("vote_average") or 0
        meta = [
            f"Release: {m.get('release_date') or 'N/A'}",
            f"Rating: {rating:.1f} ({m.get('vote_count', 0)} votes)" if rating else "Rating: N/A",
            f"Runtime: {m.get('runtime') or 'N/A'} min",
            f"Status: {m.get('status') or 'N/A'}",
            "Genres: " + (", ".join(g["name"] for g in m.get("genres", [])) or "N/A"),
            "Countries: " + (", ".join(c["name"] for c in m.get("production_countries", [])) or "N/A"),
        ]
        if m.get("tagline"):
            meta.append(f"Tagline: {m['tagline']}")
        if m.get("homepage"):
            meta.append(f"Homepage: {m['homepage']}")
        self.meta_label.configure(text="\n".join(meta))

        self.overview.configure(state="normal")
        self.overview.delete("1.0", "end")
        self.overview.insert("1.0", (m.get("overview") or "No overview available.").strip())
        self.overview.configure(state="disabled")

        cast = (m.get("credits") or {}).get("cast", [])[:8]
        if cast:
            lines = [f"- {c.get('name')} as {c.get('character') or '?'}" for c in cast]
            self.cast_label.configure(text="Top cast:\n" + "\n".join(lines))
        else:
            self.cast_label.configure(text="")

        if poster_bytes:
            try:
                img = Image.open(io.BytesIO(poster_bytes))
                img.thumbnail((220, 330))
                self.poster_img = ImageTk.PhotoImage(img)
                self.poster_label.configure(image=self.poster_img)
            except Exception:
                self.poster_label.configure(image="")
                self.poster_img = None
        else:
            self.poster_label.configure(image="")
            self.poster_img = None

        self.set_status("Ready")


def resolve_api_key():
    key = os.environ.get("TMDB_API_KEY")
    if key:
        return key
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
    MovieisApp(root, api_key)
    root.mainloop()


if __name__ == "__main__":
    main()
