import os
import sys

# Reconfigure stdout to UTF-8 on Windows to avoid UnicodeEncodeError for block chars
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
import json
import time
import re
import subprocess
import argparse
import socket
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from html import unescape

# Optional dependencies
try:
    import psutil
except ImportError:
    psutil = None

try:
    import requests
except ImportError:
    requests = None

try:
    import colorama
    from colorama import Fore, Back, Style
    try:
        # colorama >= 0.4.6: enables native VT/ANSI via SetConsoleMode without
        # wrapping stdout, so colors work in both old PowerShell and pwsh7/Windows Terminal.
        colorama.just_fix_windows_console()
    except AttributeError:
        # Older colorama fallback
        colorama.init(strip=False)
except ImportError:
    # Fallback if colorama is not installed. Output raw ANSI codes anyway,
    # as modern Windows terminals support them.
    class ANSIColor:
        def __init__(self, offset):
            self.offset = offset
        def __getattr__(self, name):
            if name == "RESET_ALL":
                return "\033[0m"
            colors = {
                "BLACK": 0, "RED": 1, "GREEN": 2, "YELLOW": 3,
                "BLUE": 4, "MAGENTA": 5, "CYAN": 6, "WHITE": 7,
                "LIGHTBLACK_EX": 60, "LIGHTRED_EX": 61, "LIGHTGREEN_EX": 62,
                "LIGHTYELLOW_EX": 63, "LIGHTBLUE_EX": 64, "LIGHTMAGENTA_EX": 65,
                "LIGHTCYAN_EX": 66, "LIGHTWHITE_EX": 67
            }
            if name in colors:
                return f"\033[{self.offset + colors[name]}m"
            return ""
            
    Fore = ANSIColor(30)
    Back = ANSIColor(40)
    class ANSIStyle:
        RESET_ALL = "\033[0m"
        def __getattr__(self, name):
            return ""
    Style = ANSIStyle()
    
    # Enable native VT processing on Windows without colorama
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TODO_FILE = os.path.join(BASE_DIR, "todo.json")
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")
SANDBOX_DIR = os.path.dirname(BASE_DIR)  # Sandbox is parent of motd folder

DEFAULT_CONFIG = {
    "username": "Louie",
    "weather_location": "Portland,ME",
    "theme": "ocean",
    "hyperlinks": True,
    "sections": {
        "system_stats": True,
        "weather": True,
        "git_status": True,
        "todos": True,
        "dev_tips": True,
        "network": True,
        "current_events": True,
        "on_this_day": True,
        "births_deaths": True,
        "random_fact": True
    }
}

DEV_TIPS = [
    # Wise Quotes (Philosophers, Scientists, Authors)
    "Quote: 'The only true wisdom is in knowing you know nothing.' — Socrates",
    "Quote: 'Out of clutter, find simplicity. From discord, find harmony. In the middle of difficulty lies opportunity.' — Albert Einstein",
    "Quote: 'Knowing yourself is the beginning of all wisdom.' — Aristotle",
    "Quote: 'Science is what you know, philosophy is what you don't know.' — Bertrand Russell",
    "Quote: 'The journey of a thousand miles begins with one step.' — Lao Tzu",
    "Quote: 'We are what we repeatedly do. Excellence, then, is not an act, but a habit.' — Aristotle",
    "Quote: 'It is the mark of an educated mind to be able to entertain a thought without accepting it.' — Aristotle",
    "Quote: 'To be yourself in a world that is constantly trying to make you something else is the greatest accomplishment.' — Ralph Waldo Emerson",
    "Quote: 'He who has a why to live can bear almost any how.' — Friedrich Nietzsche",
    "Quote: 'Nothing in life is to be feared, it is only to be understood. Now is the time to understand more, so that we may fear less.' — Marie Curie",
    "Quote: 'The mind is not a vessel to be filled, but a fire to be kindled.' — Plutarch",
    "Quote: 'Live as if you were to die tomorrow. Learn as if you were to live forever.' — Mahatma Gandhi",
    "Quote: 'Not all those who wander are lost.' — J.R.R. Tolkien",
    "Quote: 'We do not inherit the earth from our ancestors, we borrow it from our children.' — Antoine de Saint-Exupéry",
    "Quote: 'The measure of intelligence is the ability to change.' — Albert Einstein",
    "Quote: 'That which does not kill us makes us stronger.' — Friedrich Nietzsche",
    "Quote: 'A person who never made a mistake never tried anything new.' — Albert Einstein",
    "Quote: 'What you leave behind is not what is engraved in stone monuments, but what is woven into the lives of others.' — Pericles",
    "Quote: 'Patience is bitter, but its fruit is sweet.' — Jean-Jacques Rousseau",
    "Quote: 'Science is a way of thinking much more than it is a body of knowledge.' — Carl Sagan",
    "Quote: 'Somewhere, something incredible is waiting to be known.' — Carl Sagan",
    "Quote: 'We are made of starstuff. We are a way for the cosmos to know itself.' — Carl Sagan",
    "Quote: 'Nature does not hurry, yet everything is accomplished.' — Lao Tzu",
    "Quote: 'The important thing is not to stop questioning. Curiosity has its own reason for existing.' — Albert Einstein",
    "Quote: 'I have not failed. I've just found 10,000 ways that won't work.' — Thomas A. Edison",
    "Quote: 'The beginning of knowledge is the discovery of something we do not understand.' — Frank Herbert",
    "Quote: 'Simplicity is the ultimate sophistication.' — Leonardo da Vinci",
    "Quote: 'Talk is cheap. Show me the code.' — Linus Torvalds",
    
    # Practical Tips
    "Tip: Use Ctrl+Alt+/ to launch the Antigravity CLI anywhere on your system.",
    "Tip: Alt+Left-Click + Drag anywhere inside a window to move it with Alt-Drag.",
    "Tip: Alt+Right-Click + Drag anywhere inside a window to resize it.",
    "Tip: git status -sb is a great way to see a concise branch status with tracking info.",
    "Tip: In PowerShell, you can use Get-Command to quickly find executable locations.",
    "Developer Tip: Write tests before you write code. It saves time in the long run.",
    "GIS Tip: WGS84 (EPSG:4326) uses degrees, while Web Mercator (EPSG:3857) uses meters.",
    "GIS Tip: SNAP is excellent for historical remote sensing analysis of SAR and optical data."
]

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # Merge missing keys (including nested sections)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                    elif isinstance(v, dict) and isinstance(config[k], dict):
                        for sub_k, sub_v in v.items():
                            if sub_k not in config[k]:
                                config[k][sub_k] = sub_v
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG

def load_json_file(file_path, default):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json_file(file_path, data):
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

# --- Weather & Git Status Fetchers ---

WEATHER_EMOJIS = {
    "113": "☀️", "116": "⛅", "119": "☁️", "122": "☁️",
    "143": "🌫️", "248": "🌫️", "260": "🌫️", "176": "🌦️",
    "263": "🌧️", "266": "🌧️", "281": "🌧️", "284": "🌧️",
    "293": "🌧️", "296": "🌧️", "299": "🌧️", "302": "🌧️",
    "305": "🌧️", "308": "🌧️", "311": "🌧️", "314": "🌧️",
    "353": "🌦️", "356": "🌧️", "359": "🌧️", "179": "🌨️",
    "182": "🌨️", "185": "🌨️", "227": "🌨️", "230": "❄️",
    "317": "🌨️", "320": "🌨️", "323": "🌨️", "326": "🌨️",
    "329": "🌨️", "332": "🌨️", "335": "🌨️", "338": "❄️",
    "350": "🌨️", "362": "🌨️", "365": "🌨️", "368": "🌨️",
    "371": "🌨️", "374": "🌨️", "377": "🌨️", "200": "⛈️",
    "386": "⛈️", "389": "⛈️", "392": "⛈️", "395": "⛈️",
}

def fetch_weather(location):
    if not requests:
        return "Weather requires 'requests' module."
    try:
        # 1. Fetch today's weather
        url_today = f"https://wttr.in/{location}?format=%c+%t+%C"
        response_today = requests.get(url_today, timeout=3.0)
        if response_today.status_code != 200:
            return "Weather unavailable"
        
        today_str = response_today.text.strip()
        
        # Parse today's parts
        parts = today_str.split(None, 2)
        if len(parts) >= 2:
            today_emoji = parts[0]
            today_temp = parts[1]
            today_desc = parts[2] if len(parts) > 2 else ""
        else:
            today_emoji = ""
            today_temp = today_str
            today_desc = ""

        use_celsius = "°C" in today_str
        
        # 2. Fetch tomorrow's forecast
        url_json = f"https://wttr.in/{location}?format=j1"
        response_json = requests.get(url_json, timeout=3.0)
        if response_json.status_code == 200:
            r_json = response_json.json()
            tomorrow = r_json['weather'][1]
            
            if use_celsius:
                mintemp = tomorrow['mintempC']
                maxtemp = tomorrow['maxtempC']
                unit = "°C"
            else:
                mintemp = tomorrow['mintempF']
                maxtemp = tomorrow['maxtempF']
                unit = "°F"
                
            hourly = tomorrow.get('hourly', [])
            desc = ""
            code = ""
            if hourly:
                mid_idx = 4 if len(hourly) > 4 else len(hourly) // 2
                noon_data = hourly[mid_idx]
                desc = noon_data.get('weatherDesc', [{}])[0].get('value', '').strip()
                code = noon_data.get('weatherCode', '')
                
            emoji = WEATHER_EMOJIS.get(code, "☁️")
            
            # Format options
            # Format 1: Full detail
            today_full = f"Today: {today_emoji} {today_temp} {today_desc}".strip()
            tomorrow_full = f"Tomorrow: {emoji} {mintemp}..{maxtemp}{unit} {desc}".strip()
            combined = f"{today_full}  ·  {tomorrow_full}"
            
            # Check limit (51 chars visual length)
            if clean_len(combined) > 51:
                # Format 2: Drop tomorrow's description
                tomorrow_short = f"Tomorrow: {emoji} {mintemp}..{maxtemp}{unit}".strip()
                combined = f"{today_full}  ·  {tomorrow_short}"
                
            if clean_len(combined) > 51:
                # Format 3: Drop both descriptions
                today_short = f"Today: {today_emoji} {today_temp}".strip()
                combined = f"{today_short}  ·  {tomorrow_short}"
                
            if clean_len(combined) > 51:
                # Format 4: Ultra short (no prefixes)
                combined = f"{today_emoji} {today_temp}  ·  {emoji} {mintemp}..{maxtemp}{unit}"
                
            return combined
        else:
            return today_str
    except Exception as e:
        return f"Offline/Error: {str(e)}"

def check_git_repo(path):
    try:
        # Check if it's a git repo
        is_repo = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True
        )
        if is_repo.returncode != 0:
            return None
        
        # Get branch
        branch_run = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True
        )
        branch = branch_run.stdout.strip()
        if not branch:
            branch = "Detached HEAD"

        # Get status porcelain
        status_run = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True
        )
        lines = status_run.stdout.strip().split("\n")
        lines = [l for l in lines if l]
        
        modified = 0
        untracked = 0
        for line in lines:
            if line.startswith("??"):
                untracked += 1
            else:
                modified += 1

        # Check tracking remote
        remote_run = subprocess.run(
            ["git", "status", "-sb"],
            cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True
        )
        first_line = remote_run.stdout.strip().split("\n")[0] if remote_run.stdout else ""
        
        remote = "No remote"
        if "..." in first_line:
            if "[ahead" in first_line and "[behind" in first_line:
                remote = "Diverged"
            elif "[ahead" in first_line:
                ahead_count = first_line.split("[ahead")[1].split("]")[0].strip()
                remote = f"Ahead ({ahead_count})"
            elif "[behind" in first_line:
                behind_count = first_line.split("[behind")[1].split("]")[0].strip()
                remote = f"Behind ({behind_count})"
            else:
                remote = "Synced"

        # Get last commit timestamp or mtime fallback
        mtime = 0
        try:
            commit_time_run = subprocess.run(
                ["git", "log", "-1", "--format=%ct"],
                cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True
            )
            if commit_time_run.returncode == 0:
                mtime = int(commit_time_run.stdout.strip())
        except Exception:
            pass
        if not mtime:
            try:
                mtime = int(os.path.getmtime(os.path.join(path, ".git")))
            except Exception:
                try:
                    mtime = int(os.path.getmtime(path))
                except Exception:
                    mtime = 0

        return {
            "branch": branch,
            "dirty": len(lines) > 0,
            "modified": modified,
            "untracked": untracked,
            "remote": remote,
            "mtime": mtime
        }
    except Exception:
        return None

def fetch_all_git_status():
    status_map = {}
    if not os.path.exists(SANDBOX_DIR):
        return status_map
    
    # Scan subdirectories in sandbox
    for name in os.listdir(SANDBOX_DIR):
        full_path = os.path.join(SANDBOX_DIR, name)
        if os.path.isdir(full_path) and not name.startswith('.'):
            status = check_git_repo(full_path)
            if status:
                status_map[name] = status
    return status_map

# --- Wikipedia Knowledge Fetchers ---

WIKI_UA = "motd-dashboard/1.0 (personal terminal dashboard)"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1"

# Namespaces that are not real article pages (skip when picking event links)
_NON_ARTICLE_NS = (
    "File:", "Help:", "Template:", "Portal:", "Wikipedia:",
    "Category:", "Special:", "Talk:", "Module:"
)

# Current-events category importance weights (higher = more important)
CE_CATEGORY_WEIGHT = {
    "Armed conflicts and attacks": 5,
    "Disasters and accidents": 5,
    "International relations": 4,
    "Politics and elections": 4,
    "Law and crime": 3,
    "Business and economy": 3,
    "Health and environment": 3,
    "Health and medicine": 3,
    "Science and technology": 2,
    "Arts and culture": 1,
    "Sport": 1,
    "Sports": 1,
}
CE_CATEGORIES = set(CE_CATEGORY_WEIGHT.keys())


def _wiki_page_link(page):
    """Pull a normalized title + desktop URL from an onthisday 'pages' entry."""
    if not page:
        return "", ""
    title = page.get("normalizedtitle") or page.get("titles", {}).get("normalized", "")
    url = page.get("content_urls", {}).get("desktop", {}).get("page", "")
    return title, url


def fetch_on_this_day():
    """Selected historical events, notable births, and deaths for today's date."""
    result = {"events": [], "births": [], "deaths": []}
    if not requests:
        return result
    now = datetime.now()
    mm, dd = f"{now.month:02d}", f"{now.day:02d}"
    headers = {"User-Agent": WIKI_UA}
    # 'selected' = curated/notable events; births/deaths for people
    for out_key, api_type in (("events", "selected"), ("births", "births"), ("deaths", "deaths")):
        try:
            url = f"{WIKI_REST}/feed/onthisday/{api_type}/{mm}/{dd}"
            r = requests.get(url, headers=headers, timeout=4.0)
            if r.status_code != 200:
                continue
            items = r.json().get(api_type, [])
            parsed = []
            for it in items:
                text = (it.get("text") or "").strip()
                if not text:
                    continue
                title, link = _wiki_page_link((it.get("pages") or [None])[0])
                parsed.append({
                    "text": text,
                    "year": it.get("year"),
                    "title": title,
                    "url": link,
                })
            # Most recent first; cap the stored pool
            parsed.sort(key=lambda x: (x["year"] is None, -(x["year"] or 0)))
            result[out_key] = parsed[:15]
        except Exception:
            pass
    return result


# Offline "Did you know?" facts, used when Wikipedia is unreachable. Each still
# links to the relevant Wikipedia article so it stays clickable.
OFFLINE_FACTS = [
    {"title": "Octopus", "text": "An octopus has three hearts and blue, copper-based blood; two hearts pump blood to the gills and the third to the rest of the body.", "url": "https://en.wikipedia.org/wiki/Octopus"},
    {"title": "Honey", "text": "Honey never spoils -- edible honey has been found in ancient Egyptian tombs after more than 3,000 years.", "url": "https://en.wikipedia.org/wiki/Honey"},
    {"title": "Banana", "text": "Bananas are botanically berries, while strawberries are not.", "url": "https://en.wikipedia.org/wiki/Banana"},
    {"title": "Venus", "text": "A day on Venus is longer than its year -- it rotates more slowly than it orbits the Sun.", "url": "https://en.wikipedia.org/wiki/Venus"},
    {"title": "Wombat", "text": "Wombats produce cube-shaped droppings, which keep the dung from rolling away and help mark territory.", "url": "https://en.wikipedia.org/wiki/Wombat"},
    {"title": "Eiffel Tower", "text": "The Eiffel Tower can grow more than 15 cm taller in summer, as heat causes the iron to expand.", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower"},
    {"title": "Sea otter", "text": "Sea otters hold hands while sleeping so they don't drift apart on the water.", "url": "https://en.wikipedia.org/wiki/Sea_otter"},
    {"title": "Lightning", "text": "A bolt of lightning is roughly five times hotter than the surface of the Sun.", "url": "https://en.wikipedia.org/wiki/Lightning"},
    {"title": "Sloth", "text": "Sloths can hold their breath longer than dolphins by slowing their heart rate to a fraction of normal.", "url": "https://en.wikipedia.org/wiki/Sloth"},
    {"title": "Saturn", "text": "Saturn is the least dense planet in the Solar System -- it would float in water if a large enough ocean existed.", "url": "https://en.wikipedia.org/wiki/Saturn"},
    {"title": "Tardigrade", "text": "Tardigrades can survive the vacuum of space, extreme radiation, and temperatures near absolute zero.", "url": "https://en.wikipedia.org/wiki/Tardigrade"},
    {"title": "Great Wall of China", "text": "Contrary to popular belief, the Great Wall of China is not visible to the naked eye from space.", "url": "https://en.wikipedia.org/wiki/Great_Wall_of_China"},
]


def fetch_random_fact():
    """A random Wikipedia article summary, used as a 'Did you know' style fact.
    Falls back to a bundled offline fact when Wikipedia is unreachable."""
    import random
    if requests:
        headers = {"User-Agent": WIKI_UA}
        for _ in range(4):
            try:
                r = requests.get(f"{WIKI_REST}/page/random/summary", headers=headers, timeout=4.0)
                if r.status_code != 200:
                    break
                d = r.json()
                if d.get("type") == "disambiguation":
                    continue
                title = (d.get("title") or "").strip()
                extract = (d.get("extract") or "").strip()
                url = d.get("content_urls", {}).get("desktop", {}).get("page", "")
                # Skip stubs and list/index pages -- they make poor "facts"
                if len(extract) < 50 or title.lower().startswith(("list of", "index of")):
                    continue
                return {"text": extract, "title": title, "url": url}
            except Exception:
                break
    # Offline / failure fallback
    return random.choice(OFFLINE_FACTS)


class _CurrentEventsParser(HTMLParser):
    """Extracts leaf events from a Portal:Current_events day page: each event's
    text, primary article link, category, and the id of its category heading
    (used to deep-link back to that section of the day page so the reader can
    pick among the event's multiple news-source citations)."""

    # Block tags whose id should be remembered as a potential heading anchor.
    _HEADING_TAGS = {"div", "p", "h2", "h3", "h4", "h5", "section"}

    def __init__(self):
        super().__init__()
        self.li_stack = []        # one dict per open <li>
        self.events = []          # finished leaf events
        self.cur_category = ""
        self.cur_heading_id = ""  # id of the heading for cur_category
        self._last_block_id = ""  # id of the most recent block element

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self._HEADING_TAGS:
            self._last_block_id = attrs.get("id", "")
        if tag == "ul" and self.li_stack:
            # The <li> that contains this <ul> is a grouping/topic line, not a leaf
            self.li_stack[-1]["has_child_ul"] = True
        elif tag == "li":
            self.li_stack.append({"text": [], "url": "", "has_child_ul": False})
        elif tag == "a" and self.li_stack:
            href = attrs.get("href", "")
            li = self.li_stack[-1]
            if (href.startswith("/wiki/") and not li["url"]
                    and not any(href.startswith("/wiki/" + ns) for ns in _NON_ARTICLE_NS)):
                li["url"] = "https://en.wikipedia.org" + href

    def handle_endtag(self, tag):
        if tag == "li" and self.li_stack:
            li = self.li_stack.pop()
            text = re.sub(r"\s+", " ", unescape("".join(li["text"]))).strip()
            text = text.strip(" –-•")
            if text and not li["has_child_ul"]:
                self.events.append({
                    "text": text,
                    "article_url": li["url"],
                    "category": self.cur_category,
                    "anchor": self.cur_heading_id,
                })

    def handle_data(self, data):
        if self.li_stack:
            self.li_stack[-1]["text"].append(data)
        else:
            t = data.strip()
            if t in CE_CATEGORIES:
                self.cur_category = t
                self.cur_heading_id = self._last_block_id


def _parse_current_events_html(html_text):
    if not html_text:
        return []
    try:
        p = _CurrentEventsParser()
        p.feed(html_text)
        return p.events
    except Exception:
        return []


def fetch_current_events(days_back=14, today_min=3, total=8):
    """Read the last ~2 weeks of the Current Events portal, rank events by
    importance (category + recency + link presence), and always surface at
    least `today_min` of today's events."""
    out = {"events": [], "today_count": 0}
    if not requests:
        return out
    headers = {"User-Agent": WIKI_UA}
    now = datetime.now()
    all_events = []
    today_events = []
    for i in range(days_back):
        d = now - timedelta(days=i)
        day_slug = f"{d.year}_{d.strftime('%B')}_{d.day}"
        # Click target: the specific day's Current Events page, where each event
        # lists its news-source citations. Jump to the category section if the
        # page exposes a heading anchor.
        day_url = f"https://en.wikipedia.org/wiki/Portal:Current_events/{day_slug}"
        page = f"Portal:Current events/{d.year} {d.strftime('%B')} {d.day}"
        try:
            r = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "parse", "page": page, "format": "json",
                        "prop": "text", "formatversion": "2"},
                headers=headers, timeout=4.0,
            )
            if r.status_code != 200:
                continue
            html_text = r.json().get("parse", {}).get("text", "")
            if isinstance(html_text, dict):
                html_text = html_text.get("*", "")
            for e in _parse_current_events_html(html_text):
                e["days_ago"] = i
                e["date"] = d.strftime("%b %d")
                anchor = e.get("anchor") or ""
                e["url"] = day_url + (f"#{anchor}" if anchor else "")
                all_events.append(e)
                if i == 0:
                    today_events.append(e)
        except Exception:
            pass

    for e in all_events:
        cw = CE_CATEGORY_WEIGHT.get(e["category"], 2)
        e["score"] = cw * 10 + (2 if e.get("article_url") else 0) + min(len(e["text"]) // 50, 3) + max(0, 5 - e["days_ago"])

    chosen, seen = [], set()

    def add(ev):
        key = ev["text"][:60].lower()
        if key in seen:
            return
        seen.add(key)
        chosen.append(ev)

    for e in sorted(today_events, key=lambda x: -x["score"])[:today_min]:
        add(e)
    for e in sorted(all_events, key=lambda x: -x["score"]):
        if len(chosen) >= total:
            break
        add(e)

    out["events"] = chosen
    out["today_count"] = sum(1 for e in chosen if e.get("days_ago") == 0)
    return out


def update_cache():
    config = load_config()
    weather = fetch_weather(config.get("weather_location", "Portland,ME"))
    git_status = fetch_all_git_status()
    
    # Active Network Context
    ip = get_local_ip()
    conn_name = get_network_connection_name(ip)
    
    # Measure network speed in background (0.5s duration for stability)
    bg_up, bg_down = 0, 0
    if psutil:
        try:
            c1 = psutil.net_io_counters()
            time.sleep(0.5)
            c2 = psutil.net_io_counters()
            bg_up = max(0, (c2.bytes_sent - c1.bytes_sent) / 0.5)
            bg_down = max(0, (c2.bytes_recv - c1.bytes_recv) / 0.5)
        except Exception:
            pass

    # Load existing cache to preserve history
    existing_cache = load_json_file(CACHE_FILE, {})
    up_history = existing_cache.get("up_history", [])
    down_history = existing_cache.get("down_history", [])
    if not isinstance(up_history, list):
        up_history = []
    if not isinstance(down_history, list):
        down_history = []

    up_history.append(bg_up)
    down_history.append(bg_down)
    if len(up_history) > 18:
        up_history = up_history[-18:]
    if len(down_history) > 18:
        down_history = down_history[-18:]

    # Wikipedia knowledge feeds. On a failed/empty fetch, keep the last good
    # cached values (offline fallback) so boxes don't blank out during outages.
    on_this_day = fetch_on_this_day()
    if not any(on_this_day.get(k) for k in ("events", "births", "deaths")):
        on_this_day = existing_cache.get("on_this_day") or on_this_day
    current_events = fetch_current_events()
    if not current_events.get("events"):
        current_events = existing_cache.get("current_events") or current_events
    # Random fact always returns something (bundled offline facts as fallback)
    random_fact = fetch_random_fact()

    cache_data = {
        "timestamp": time.time(),
        "weather": weather,
        "git_status": git_status,
        "conn_name": conn_name,
        "ip": ip,
        "up_history": up_history,
        "down_history": down_history,
        "on_this_day": on_this_day,
        "random_fact": random_fact,
        "current_events": current_events,
        "data_date": datetime.now().strftime("%Y-%m-%d"),
    }
    save_json_file(CACHE_FILE, cache_data)
    return cache_data

# --- Todo List Operations ---

def load_todos():
    todos = load_json_file(TODO_FILE, [])
    todo_dir = os.path.expanduser(os.path.join("~", "todo"))
    if os.path.exists(todo_dir) and os.path.isdir(todo_dir):
        try:
            files = [f for f in os.listdir(todo_dir) if os.path.isfile(os.path.join(todo_dir, f))]
            modified = False
            for f in files:
                name_without_ext, _ = os.path.splitext(f)
                task_text = name_without_ext.replace("_", " ").replace("-", " ")
                if task_text:
                    task_text = task_text[0].upper() + task_text[1:]
                
                exists = any(t.get("text") == task_text or t.get("file") == f for t in todos)
                if not exists:
                    todos.append({
                        "text": task_text,
                        "done": False,
                        "created_at": time.time(),
                        "file": f
                    })
                    modified = True
            
            # If a file has been deleted from the todo folder, mark it as done if it isn't already
            for t in todos:
                if "file" in t and not t["done"]:
                    file_path = os.path.join(todo_dir, t["file"])
                    if not os.path.exists(file_path):
                        t["done"] = True
                        modified = True
                        
            if modified:
                save_json_file(TODO_FILE, todos)
        except Exception:
            pass
    return todos

def manage_todo(action, args):
    todos = load_todos()
    
    if action == "add":
        task_text = " ".join(args)
        if not task_text:
            print("Error: Task description cannot be empty.")
            return
        due, clean_text = get_todo_due({"text": task_text})
        todo_item = {
            "text": clean_text if due else task_text,
            "done": False,
            "created_at": time.time()
        }
        if due:
            todo_item["due"] = due
        todos.append(todo_item)
        save_json_file(TODO_FILE, todos)
        print(f"Added task: '{clean_text if due else task_text}'" + (f" (Due: {due})" if due else ""))
        
    elif action == "list":
        if not todos:
            print("No tasks in your todo list.")
            return
        print(f"\n{Fore.CYAN}--- TODO LIST ---{Style.RESET_ALL}")
        for idx, todo in enumerate(todos, 1):
            due, clean_text = get_todo_due(todo)
            status = "[x]" if todo["done"] else "[ ]"
            color = Fore.GREEN if todo["done"] else Fore.YELLOW
            due_str = f" ({Fore.RED}Due: {due}{color})" if due else ""
            print(f"{color}{idx}. {status} {clean_text}{due_str}{Style.RESET_ALL}")
        print()
        
    elif action == "check":
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(todos):
                todos[idx]["done"] = not todos[idx]["done"]
                save_json_file(TODO_FILE, todos)
                status = "completed" if todos[idx]["done"] else "incomplete"
                print(f"Task {idx + 1} marked as {status}.")
            else:
                print("Error: Invalid task index.")
        except (ValueError, IndexError):
            print("Usage: --todo check <index>")
            
    elif action == "delete":
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(todos):
                removed = todos.pop(idx)
                save_json_file(TODO_FILE, todos)
                print(f"Deleted task: '{removed['text']}'")
            else:
                print("Error: Invalid task index.")
        except (ValueError, IndexError):
            print("Usage: --todo delete <index>")
            
    elif action == "clear":
        active_todos = [t for t in todos if not t["done"]]
        cleared_count = len(todos) - len(active_todos)
        save_json_file(TODO_FILE, active_todos)
        print(f"Cleared {cleared_count} completed tasks.")

# --- Visual Renderers ---

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_network_connection_name(ip):
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        if res.returncode == 0:
            out = res.stdout.decode('utf-8', errors='ignore')
            if not out.strip():
                out = res.stdout.decode('cp850', errors='ignore')
            ssid = None
            signal = None
            state = None
            for line in out.split("\n"):
                line = line.strip()
                if line.startswith("SSID"):
                    ssid = line.split(":", 1)[1].strip()
                elif line.startswith("Signal"):
                    signal = line.split(":", 1)[1].strip()
                elif line.startswith("State"):
                    state = line.split(":", 1)[1].strip()
            if ssid and state == "connected":
                return f"📶 Wi-Fi ({ssid})" + (f" - {signal}" if signal else "")
    except Exception:
        pass
    
    if psutil:
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.address == ip:
                        if "ethernet" in interface.lower() or "eth" in interface.lower():
                            return f"🔌 Ethernet ({interface})"
                        return f"🌐 Network ({interface})"
        except Exception:
            pass
    return "Disconnected"

def get_instant_network_speed(duration=0.05):
    if not psutil:
        return 0
    try:
        c1 = psutil.net_io_counters()
        time.sleep(duration)
        c2 = psutil.net_io_counters()
        sent = c2.bytes_sent - c1.bytes_sent
        recv = c2.bytes_recv - c1.bytes_recv
        return (sent + recv) / duration
    except Exception:
        return 0

def get_instant_network_io(duration=0.05):
    """Return (upload_bytes_per_sec, download_bytes_per_sec)."""
    if not psutil:
        return (0, 0)
    try:
        c1 = psutil.net_io_counters()
        time.sleep(duration)
        c2 = psutil.net_io_counters()
        up = (c2.bytes_sent - c1.bytes_sent) / duration
        down = (c2.bytes_recv - c1.bytes_recv) / duration
        return (max(0, up), max(0, down))
    except Exception:
        return (0, 0)

def get_readable_speed(bytes_per_sec):
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"

def draw_vertical_chart(history, width=18):
    if len(history) < width:
        history = [0] * (width - len(history)) + history
    elif len(history) > width:
        history = history[-width:]
        
    max_val = max(history) if history else 0
    if max_val == 0:
        max_val = 1
        
    rows = ["", "", ""]
    for v in history:
        h = int(round((v / max_val) * 6))
        # Top row
        if h >= 6:
            rows[0] += "█"
        elif h == 5:
            rows[0] += "▄"
        else:
            rows[0] += " "
            
        # Middle row
        if h >= 4:
            rows[1] += "█"
        elif h == 3:
            rows[1] += "▄"
        else:
            rows[1] += " "
            
        # Bottom row
        if h >= 2:
            rows[2] += "█"
        elif h == 1:
            rows[2] += "▄"
        else:
            rows[2] += " "
    return rows

SPARK_CHARS = " ▁▂▃▄▅▆▇█"

def draw_sparkline(history, max_val, width=18):
    """Render a single-line sparkline. Bars are scaled against a shared
    max_val so multiple series can be compared accurately against each other."""
    history = list(history)
    if len(history) < width:
        history = [0] * (width - len(history)) + history
    elif len(history) > width:
        history = history[-width:]

    if max_val <= 0:
        return SPARK_CHARS[0] * width

    line = ""
    levels = len(SPARK_CHARS) - 1  # 8
    for v in history:
        frac = v / max_val
        if frac < 0:
            frac = 0
        elif frac > 1:
            frac = 1
        idx = int(round(frac * levels))
        # Any non-zero usage should show at least the smallest bar
        if idx == 0 and v > 0:
            idx = 1
        line += SPARK_CHARS[idx]
    return line

def draw_bar(percent, width=15):
    filled = int(percent / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar

def draw_colored_bar(percent, colors, width=15):
    filled = int(percent / 100 * width)
    if percent < 75:
        color = Fore.GREEN
    elif percent < 90:
        color = Fore.YELLOW
    else:
        color = Fore.RED
    bar = color + "█" * filled + Fore.LIGHTBLACK_EX + "░" * (width - filled) + colors["val"]
    return bar

def get_uptime():
    if not psutil:
        return "Uptime unavailable (requires psutil)"
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except Exception:
        return "Error getting uptime"

def get_system_stats():
    stats = {}
    if not psutil:
        return None
    try:
        stats["cpu_pct"] = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        stats["ram_pct"] = mem.percent
        stats["ram_used"] = mem.used / (1024**3)
        stats["ram_total"] = mem.total / (1024**3)
        
        # Disk usage of the main drive (or sandbox drive)
        try:
            disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
            stats["disk_pct"] = disk.percent
            stats["disk_used"] = disk.used / (1024**3)
            stats["disk_total"] = disk.total / (1024**3)
        except Exception:
            stats["disk_pct"] = 0
            stats["disk_used"] = 0
            stats["disk_total"] = 0
            
        stats["uptime"] = get_uptime()
    except Exception:
        return None
    return stats

def get_theme_colors(theme):
    if theme == "ocean":
        return {
            "border": Fore.CYAN,
            "label": Fore.BLUE,
            "val": Fore.WHITE,
            "highlight": Fore.LIGHTCYAN_EX,
            "sub": Fore.LIGHTBLUE_EX
        }
    elif theme == "forest":
        return {
            "border": Fore.GREEN,
            "label": Fore.YELLOW,
            "val": Fore.WHITE,
            "highlight": Fore.LIGHTGREEN_EX,
            "sub": Fore.LIGHTYELLOW_EX
        }
    # Default (Classic Dark/Purple)
    return {
        "border": Fore.MAGENTA,
        "label": Fore.CYAN,
        "val": Fore.WHITE,
        "highlight": Fore.LIGHTMAGENTA_EX,
        "sub": Fore.LIGHTCYAN_EX
    }

# Helper functions for layout and visual formatting
import re
import textwrap

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
# OSC 8 hyperlink sequences: ESC ] 8 ; params ; URI  (terminated by BEL or ESC \)
OSC8_ESCAPE = re.compile(r'\x1b\]8;[^\x07\x1b]*(?:\x07|\x1b\\)')


def hyperlink(text, url, enabled=True):
    """Wrap visible text in an OSC 8 terminal hyperlink (clickable in modern
    terminals like Windows Terminal). Falls back to plain text when disabled
    or when no URL is available."""
    if not enabled or not url:
        return text
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def print_entry(bullet, text, url, colors, links_on, text_color=None,
                indent="  ", wrap=True):
    """Render a single (optionally clickable, optionally wrapped) list entry
    inside a box. The whole text becomes the clickable link target."""
    text_color = text_color if text_color is not None else colors["val"]
    bullet_vis = clean_len(bullet)
    # width available for the text after indent + bullet + trailing pad
    avail = INNER_WIDTH - clean_len(indent) - bullet_vis - 2
    if avail < 10:
        avail = 10
    if wrap:
        lines = textwrap.wrap(text, width=avail) or [""]
    else:
        lines = [truncate_str(text, avail)]
    cont_pad = " " * (clean_len(indent) + bullet_vis)
    for i, ln in enumerate(lines):
        shown = hyperlink(ln, url, links_on) if url else ln
        if i == 0:
            left = f"{indent}{bullet}{text_color}{shown}"
        else:
            left = f"{cont_pad}{text_color}{shown}"
        print(format_row(left, "", colors))


def get_todo_due(todo):
    due = todo.get("due")
    text = todo.get("text", "")
    if due:
        return due, text
        
    # On-the-fly extraction for backwards compatibility
    patterns = [
        r'(?i)\(deadline:\s*([^\)]+)\)',
        r'(?i)\(due:\s*([^\)]+)\)',
        r'(?i)\bdeadline:\s*([^|\(\)]+)',
        r'(?i)\bdue:\s*([^|\(\)]+)',
        r'(?i)\bby:\s*([^|\(\)]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            due = match.group(1).strip()
            # Clean text to remove the matched part
            clean_text = text.replace(match.group(0), "").strip()
            # Clean up empty parens
            clean_text = re.sub(r'\(\s*\)', '', clean_text).strip()
            # Clean up trailing punctuation
            clean_text = re.sub(r'\s*[,;.-]$', '', clean_text).strip()
            return due, clean_text
            
    return None, text

BOX_WIDTH = 64
INNER_WIDTH = BOX_WIDTH - 2  # 62

import unicodedata

def to_superscript(text):
    mapping = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '-': '⁻', ':': ':', ' ': ' ', 'U': 'ᵁ', 'T': 'ᵀ', 'C': 'ᶜ',
        'A': 'ᴬ', 'B': 'ᴮ', 'D': 'ᴰ', 'E': 'ᴱ', 'F': 'ᶠ', 'G': 'ᴳ',
        'H': 'ᴴ', 'I': 'ᴵ', 'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ', 'M': 'ᴹ',
        'N': 'ᴺ', 'O': 'ᴼ', 'P': 'ᴾ', 'Q': 'ᵠ', 'R': 'ᴿ', 'S': 'ˢ',
        'V': 'ⱽ', 'W': 'ᵂ', 'X': 'ˣ', 'Y': 'ʸ', 'Z': 'ᶻ',
        'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ', 'f': 'ᶠ',
        'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ', 'k': 'ᵏ', 'l': 'ˡ',
        'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ', 'p': 'ᵖ', 'q': 'ᵠ', 'r': 'ʳ',
        's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ', 'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ',
        'y': 'ʸ', 'z': 'ᶻ'
    }
    return "".join(mapping.get(c, c) for c in text)

def clean_len(s):
    # Strip OSC 8 hyperlink wrappers and CSI color codes so width math counts
    # only the visible characters.
    plain = ANSI_ESCAPE.sub('', OSC8_ESCAPE.sub('', s))
    w = 0
    for char in plain:
        # Check if the character is a Wide or Full-width character (like emojis)
        if unicodedata.east_asian_width(char) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w



def pad_ansi(s, width, align="left"):
    vis_len = clean_len(s)
    padding = width - vis_len
    if padding <= 0:
        return s
    
    if align == "left":
        return s + " " * padding
    elif align == "right":
        return " " * padding + s
    else: # center
        left_pad = padding // 2
        right_pad = padding - left_pad
        return " " * left_pad + s + " " * right_pad

def truncate_str(s, max_len):
    if len(s) > max_len:
        return s[:max_len-3] + "..."
    return s

def make_border_top(title=None, colors=None):
    border_color = colors["border"] if colors else ""
    title_color = colors["highlight"] if colors else ""
    reset = Style.RESET_ALL if colors else ""
    
    if not title:
        return f"{border_color}┌" + "─" * INNER_WIDTH + f"┐{reset}"
        
    vis_title_len = clean_len(title)
    dash_count = INNER_WIDTH - 3 - vis_title_len
    if dash_count < 0:
        title = truncate_str(title, INNER_WIDTH - 6)
        vis_title_len = clean_len(title)
        dash_count = INNER_WIDTH - 3 - vis_title_len
        
    return f"{border_color}┌─ {title_color}{title}{border_color} " + "─" * dash_count + f"┐{reset}"

def make_border_bottom(colors=None):
    border_color = colors["border"] if colors else ""
    reset = Style.RESET_ALL if colors else ""
    return f"{border_color}└" + "─" * INNER_WIDTH + f"┘{reset}"

def format_row(left, right="", colors=None):
    border_color = colors["border"] if colors else ""
    reset = Style.RESET_ALL if colors else ""
    
    vis_left = clean_len(left)
    vis_right = clean_len(right)
    
    space_count = INNER_WIDTH - vis_left - vis_right
    if space_count < 0:
        space_count = 0
        
    return f"{border_color}│{reset}{left}" + " " * space_count + f"{right}{border_color}│{reset}"

def print_dashboard():
    config = load_config()
    colors = get_theme_colors(config.get("theme", "ocean"))
    sec = config.get("sections", {})
    links_on = config.get("hyperlinks", True)

    # 1. ASCII/Welcome Header
    print(make_border_top(None, colors))
    
    logo_line_1 = f"{colors['highlight']}▒█░░▒█ ▒█ ▒█▄░▒█ ▀▀▒█▀ ▒█▀▀▀ ▒█▀▀▄ ▒█▄░▄█ ▒█░░▒█ ▀▀▒█▀ ▒█▀▀▀"
    logo_line_2 = f"{colors['highlight']}▒█▒█▒█ ▒█ ▒█▒█▒█ ░░▒█░ ▒█▀▀░ ▒█▄▄▀ ▒█▒█▒█ ▒█░░▒█ ░░▒█░ ▒█▀▀░"
    logo_line_3 = f"{colors['highlight']}░▀▄▀▄▀ ▒█ ▒█░░▀█ ░░▒█░ ▒█▄▄▄ ▒█░▒█ ▒█░░░█ ░▀▄▄▄▀ ░░▒█░ ▒█▄▄▄"
    
    print(format_row(pad_ansi(logo_line_1, INNER_WIDTH, "center"), "", colors))
    print(format_row(pad_ansi(logo_line_2, INNER_WIDTH, "center"), "", colors))
    print(format_row(pad_ansi(logo_line_3, INNER_WIDTH, "center"), "", colors))
    print(format_row("", "", colors))
    
    # Date, User and Uptime
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greeting = "Good Morning"
    elif 12 <= hour < 18:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"
    user_str = f"{greeting}, {config.get('username', 'Louie')}!"
    
    # Adapt date format to fit
    for date_fmt in [
        "%A, %b %d %Y | %I:%M %p",
        "%a, %b %d %Y | %I:%M %p",
        "%b %d %Y | %I:%M %p",
        "%b %d | %I:%M %p"
    ]:
        now_str = datetime.now().strftime(date_fmt)
        if (2 + len(user_str)) + (len(now_str) + 2) <= INNER_WIDTH:
            break
    else:
        now_str = datetime.now().strftime("%b %d | %I:%M %p")
        
    left_welcome = f"  {colors['highlight']}{user_str}"
    right_welcome = f"{colors['sub']}{now_str}  "
    print(format_row(left_welcome, right_welcome, colors))
    
    # UTC timestamp in superscript/small font on a separate line in magenta color
    utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    utc_small = to_superscript(utc_str)
    right_utc = f"{Fore.MAGENTA}{utc_small}  "
    print(format_row("", right_utc, colors))
    
    print(make_border_bottom(colors))
    
    # Load Cache
    cache = load_json_file(CACHE_FILE, {"timestamp": 0, "weather": "Fetching...", "git_status": {}, "conn_name": "Disconnected", "ip": "127.0.0.1", "up_history": [], "down_history": []})
    
    # Measure instant up/down speed (50ms check) on shell startup
    current_up, current_down = get_instant_network_io(0.05)

    # Update cache's up/down history and save
    up_history = cache.get("up_history", [])
    down_history = cache.get("down_history", [])
    if not isinstance(up_history, list):
        up_history = []
    if not isinstance(down_history, list):
        down_history = []
    up_history.append(current_up)
    down_history.append(current_down)
    if len(up_history) > 18:
        up_history = up_history[-18:]
    if len(down_history) > 18:
        down_history = down_history[-18:]
    cache["up_history"] = up_history
    cache["down_history"] = down_history
    save_json_file(CACHE_FILE, cache)
    
    # Refresh if cache is older than 15 mins, missing, or from a previous day
    # (the knowledge feeds are date-specific and should roll over at midnight).
    cache_age = time.time() - cache.get("timestamp", 0)
    stale_day = cache.get("data_date") != datetime.now().strftime("%Y-%m-%d")
    if cache_age > 900 or stale_day or not os.path.exists(CACHE_FILE):
        # Spawn silent background updater
        try:
            subprocess.Popen(
                [sys.executable, __file__, "--update"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0
            )
        except Exception:
            pass

    # 2. System Resource Box
    stats = get_system_stats()
    if sec.get("system_stats") and stats:
        cpu_bar = draw_colored_bar(stats["cpu_pct"], colors)
        ram_bar = draw_colored_bar(stats["ram_pct"], colors)
        disk_bar = draw_colored_bar(stats["disk_pct"], colors)
        
        print(make_border_top("System Health", colors))
        
        cpu_left = f"  {colors['label']}CPU {colors['val']}[{cpu_bar}] {stats['cpu_pct']:>5.1f}%"
        cpu_right = f"{colors['label']}Uptime: {colors['val']}{stats['uptime']}  "
        print(format_row(cpu_left, cpu_right, colors))
        
        ram_left = f"  {colors['label']}RAM {colors['val']}[{ram_bar}] {stats['ram_pct']:>5.1f}%"
        ram_right = f"{colors['val']}({stats['ram_used']:.1f}/{stats['ram_total']:.1f} GB)  "
        print(format_row(ram_left, ram_right, colors))
        
        is_critical = stats["disk_pct"] >= 90
        disk_left = f"  {colors['label']}Disk{colors['val']}[{disk_bar}] {stats['disk_pct']:>5.1f}%"
        if is_critical:
            disk_right = f"{Fore.RED}(CRITICAL) {colors['val']}({stats['disk_used']:.1f}/{stats['disk_total']:.1f} GB)  "
        else:
            disk_right = f"{colors['val']}({stats['disk_used']:.1f}/{stats['disk_total']:.1f} GB)  "
        print(format_row(disk_left, disk_right, colors))
        
        print(make_border_bottom(colors))

    # 2b. Network Status Box
    if sec.get("network", True):
        conn_name = cache.get("conn_name", "Disconnected")
        conn_name = truncate_str(conn_name, 25)
        ip = cache.get("ip", "127.0.0.1")
        
        print(make_border_top("Network Status", colors))
        
        conn_left = f"  {colors['label']}Network: {colors['val']}{conn_name}"
        conn_right = f"{colors['label']}IP: {colors['val']}{ip}  "
        print(format_row(conn_left, conn_right, colors))

        # Distinct colors per series, consistent across themes
        DOWN_COLOR = Fore.LIGHTCYAN_EX
        UP_COLOR = Fore.LIGHTMAGENTA_EX

        # Shared scale so the two series are directly comparable: a tall
        # download bar next to a short upload bar reflects real relative usage.
        shared_max = max([0] + up_history + down_history)

        down_spark = draw_sparkline(down_history, shared_max, width=18)
        up_spark = draw_sparkline(up_history, shared_max, width=18)

        peak_down = max(down_history) if down_history else 0
        peak_up = max(up_history) if up_history else 0

        # Download row (cyan)
        d_left = f"  {DOWN_COLOR}↓ {colors['label']}Down: {colors['val']}{get_readable_speed(current_down):>9}"
        d_right = f"{DOWN_COLOR}{down_spark}  "
        print(format_row(d_left, d_right, colors))

        # Upload row (magenta)
        u_left = f"  {UP_COLOR}↑ {colors['label']}Up:   {colors['val']}{get_readable_speed(current_up):>9}"
        u_right = f"{UP_COLOR}{up_spark}  "
        print(format_row(u_left, u_right, colors))

        # Peak / legend row
        peak_left = (f"  {colors['sub']}peak {DOWN_COLOR}↓{colors['sub']} {get_readable_speed(peak_down)}"
                     f" · {UP_COLOR}↑{colors['sub']} {get_readable_speed(peak_up)}")
        peak_right = f"{colors['sub']}18 samples  "
        print(format_row(peak_left, peak_right, colors))

        print(make_border_bottom(colors))

    # 3. Weather & Tips Row
    if sec.get("weather") or sec.get("dev_tips"):
        print(make_border_top("Status & Insights", colors))
        
        if sec.get("weather"):
            weather_val = cache.get("weather", "Loading weather...")
            weather_left = f"  {colors['label']}Weather: {colors['val']}{weather_val}"
            print(format_row(weather_left, "", colors))
            
        if sec.get("dev_tips"):
            import random
            tip = random.choice(DEV_TIPS)
            # Wrap tip dynamically to inner width - 13 characters for label/indent
            wrapped_lines = textwrap.wrap(tip, width=INNER_WIDTH - 13)
            if wrapped_lines:
                first_line = f"  {colors['label']}Tip/Quote: {Fore.LIGHTBLACK_EX}{wrapped_lines[0]}"
                print(format_row(first_line, "", colors))
                for line in wrapped_lines[1:]:
                    indent_line = f"             {Fore.LIGHTBLACK_EX}{line}"
                    print(format_row(indent_line, "", colors))
                
        print(make_border_bottom(colors))

    import random

    # 3b. Current Events (curated from Wikipedia's Current Events portal)
    if sec.get("current_events", True):
        ce = cache.get("current_events") or {}
        ce_events = ce.get("events", []) or []
        print(make_border_top("Current Events · Wikipedia", colors))
        if ce_events:
            for e in ce_events[:6]:
                txt = e.get("text", "")
                if e.get("days_ago", 0) != 0 and e.get("date"):
                    txt = f"{txt} ({e['date']})"
                print_entry(f"{colors['highlight']}• ", txt, e.get("url", ""),
                            colors, links_on, wrap=False)
        else:
            msg = "Loading current events..." if not cache.get("data_date") else "No current events available."
            print(format_row(f"  {colors['sub']}{msg}", "", colors))
        print(make_border_bottom(colors))

    # 3c. On This Day in History
    if sec.get("on_this_day", True):
        otd = cache.get("on_this_day") or {}
        ev = otd.get("events", []) or []
        print(make_border_top("On This Day in History", colors))
        if ev:
            sample = random.sample(ev, min(4, len(ev)))
            sample.sort(key=lambda x: -(x.get("year") or 0))
            for e in sample:
                yr = e.get("year")
                bullet = f"{colors['sub']}{(str(yr) + ' ') if yr else ''}{colors['label']}— "
                print_entry(bullet, e.get("text", ""), e.get("url", ""),
                            colors, links_on, wrap=False)
        else:
            msg = "Loading historical events..." if not cache.get("data_date") else "Unavailable."
            print(format_row(f"  {colors['sub']}{msg}", "", colors))
        print(make_border_bottom(colors))

    # 3d. Notable Births & Deaths on this day
    if sec.get("births_deaths", True):
        otd = cache.get("on_this_day") or {}
        births = otd.get("births", []) or []
        deaths = otd.get("deaths", []) or []
        print(make_border_top("Born & Died on This Day", colors))
        if births or deaths:
            for e in (random.sample(births, min(2, len(births))) if births else []):
                yr = e.get("year")
                bullet = f"{Fore.LIGHTGREEN_EX}★ {colors['sub']}{(str(yr) + '  ') if yr else ''}"
                print_entry(bullet, e.get("text", ""), e.get("url", ""),
                            colors, links_on, wrap=False)
            for e in (random.sample(deaths, min(2, len(deaths))) if deaths else []):
                yr = e.get("year")
                bullet = f"{Fore.LIGHTBLACK_EX}† {colors['sub']}{(str(yr) + '  ') if yr else ''}"
                print_entry(bullet, e.get("text", ""), e.get("url", ""),
                            colors, links_on, wrap=False)
        else:
            msg = "Loading births & deaths..." if not cache.get("data_date") else "Unavailable."
            print(format_row(f"  {colors['sub']}{msg}", "", colors))
        print(make_border_bottom(colors))

    # 3e. Did You Know? (random Wikipedia fact)
    if sec.get("random_fact", True):
        rf = cache.get("random_fact")
        print(make_border_top("Did You Know?", colors))
        if rf and rf.get("text"):
            title = rf.get("title", "")
            body = f"{title}: {rf['text']}" if title else rf["text"]
            print_entry(f"{colors['highlight']}◆ ", body, rf.get("url", ""),
                        colors, links_on, wrap=True)
        else:
            msg = "Loading a fact..." if not cache.get("data_date") else "Unavailable."
            print(format_row(f"  {colors['sub']}{msg}", "", colors))
        print(make_border_bottom(colors))

    # 4. Git Repository Alerts
    if sec.get("git_status"):
        git_data = cache.get("git_status", {})
        if git_data:
            print(make_border_top("Git Repository Tracker", colors))
            # Sort repos by mtime descending (most recently updated first)
            sorted_repos = []
            for repo, rstatus in git_data.items():
                if rstatus:
                    mtime = rstatus.get("mtime", 0)
                    sorted_repos.append((repo, rstatus, mtime))
            sorted_repos.sort(key=lambda x: x[2], reverse=True)
            
            # Select at most 6 most recently updated ones with unique first 4 letters
            selected_repos = []
            seen_prefixes = set()
            for repo, rstatus, mtime in sorted_repos:
                prefix = repo[:4].lower()
                if len(prefix) < 4:
                    prefix = repo.lower()
                if prefix not in seen_prefixes:
                    seen_prefixes.add(prefix)
                    selected_repos.append((repo, rstatus))
                    if len(selected_repos) == 6:
                        break
                        
            shown_repos = {repo for repo, _ in selected_repos}
            
            clean_count = 0
            # Count clean repos from those not selected
            for repo, rstatus in git_data.items():
                if rstatus and repo not in shown_repos:
                    is_clean = not rstatus["dirty"] and rstatus["remote"] == "Synced"
                    if is_clean:
                        clean_count += 1
                        
            shown_any = False
            for repo, rstatus in selected_repos:
                is_clean = not rstatus["dirty"] and rstatus["remote"] == "Synced"
                if is_clean:
                    clean_count += 1
                    continue
                    
                shown_any = True
                branch = rstatus["branch"]
                remote = rstatus["remote"]
                
                # Highlight status
                if rstatus["dirty"]:
                    # Dirty (modified / untracked)
                    mod_count = rstatus.get('modified', 0)
                    unt_count = rstatus.get('untracked', 0)
                    status_str = f"{Fore.YELLOW}+{mod_count}m +{unt_count}u{colors['val']}"
                else:
                    status_str = f"{Fore.GREEN}Clean{colors['val']}"
                    
                # Remote coloring
                if remote == "Synced":
                    rem_str = f"{Fore.GREEN}Synced{colors['val']}"
                elif "Ahead" in remote:
                    rem_str = f"{Fore.LIGHTGREEN_EX}{remote}{colors['val']}"
                elif "Behind" in remote:
                    rem_str = f"{Fore.RED}{remote}{colors['val']}"
                else:
                    rem_str = f"{Fore.LIGHTBLACK_EX}{remote}{colors['val']}"
                    
                repo_name = truncate_str(repo, 15)
                branch_name = truncate_str(branch, 9)
                
                left_part = f"  • {colors['highlight']}{repo_name:<15}  {colors['sub']}{branch_name:<9}"
                right_part = pad_ansi(status_str, 13, "left") + "  " + pad_ansi(rem_str, 10, "right")
                
                print(format_row(left_part, right_part, colors))
            
            if clean_count > 0:
                footer_str = f"  {Fore.LIGHTBLACK_EX}... and {clean_count} other repositories are clean."
                print(format_row(footer_str, "", colors))
            elif not shown_any:
                no_issues_str = f"  {Fore.GREEN}✓ All repositories are clean and synced."
                print(format_row(no_issues_str, "", colors))
                
            print(make_border_bottom(colors))

    # 5. Local Todos
    if sec.get("todos"):
        todos = load_todos()
        pending = [t for t in todos if not t["done"]]
        
        if pending:
            title = f"Current Todo Checklist ({len(pending)} pending)"
            print(make_border_top(title, colors))
            for idx, todo in enumerate(pending[:5], 1):
                due, clean_text = get_todo_due(todo)
                
                # Dynamically calculate space available for task text to prevent overflow
                right_len = 7 + len(due) if due else 0
                left_base_len = 8 + len(str(idx))
                max_text_len = INNER_WIDTH - left_base_len - right_len - 2
                
                if len(clean_text) > max_text_len:
                    clean_text = clean_text[:max_text_len - 3] + "..."
                    
                left = f"  {Fore.YELLOW}{idx}. [ ] {colors['val']}{clean_text}"
                right = f"{Fore.RED}Due: {due}  " if due else ""
                print(format_row(left, right, colors))
            if len(pending) > 5:
                more_str = f"  {Fore.LIGHTBLACK_EX}... and {len(pending) - 5} more. Run 'motd --todo list' to view."
                print(format_row(more_str, "", colors))
            print(make_border_bottom(colors))
        else:
            print(make_border_top("Todo Checklist", colors))
            left = f"  {Fore.GREEN}✓ All tasks completed! Use '--todo add' to add."
            print(format_row(left, "", colors))
            print(make_border_bottom(colors))

    print()

def main():
    parser = argparse.ArgumentParser(description="Terminal MOTD (Message of the Day) Dashboard Utility")
    parser.add_argument("--update", action="store_true", help="Manually refresh weather and git status cache")
    
    # Todo subparsers
    parser.add_argument("--todo", choices=["add", "list", "check", "delete", "clear"], help="Manage your todo checklist")
    parser.add_argument("todo_args", nargs="*", help="Arguments for the todo subcommand")
    
    args = parser.parse_args()
    
    if args.update:
        # Run synchronous update
        update_cache()
    elif args.todo:
        manage_todo(args.todo, args.todo_args)
    else:
        print_dashboard()

if __name__ == "__main__":
    main()
# Network Status box shows separate upload/download sparklines (shared-scaled).
