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
import subprocess
import argparse
import socket
from datetime import datetime

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
    colorama.init()
except ImportError:
    # Fallback if colorama is not installed
    class EmptyColor:
        def __getattr__(self, name):
            return ""
    Fore = Back = Style = EmptyColor()

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
    "sections": {
        "system_stats": True,
        "weather": True,
        "git_status": True,
        "todos": True,
        "dev_tips": True,
        "network": True
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

def fetch_weather(location):
    if not requests:
        return "Weather requires 'requests' module."
    try:
        # Fetch simple format: emoji/condition, temperature, description
        url = f"https://wttr.in/{location}?format=%c+%t+%C"
        response = requests.get(url, timeout=2.0)
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        return f"Offline/Error: {str(e)}"
    return "Weather unavailable"

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

        return {
            "branch": branch,
            "dirty": len(lines) > 0,
            "modified": modified,
            "untracked": untracked,
            "remote": remote
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

    cache_data = {
        "timestamp": time.time(),
        "weather": weather,
        "git_status": git_status,
        "conn_name": conn_name,
        "ip": ip,
        "up_history": up_history,
        "down_history": down_history
    }
    save_json_file(CACHE_FILE, cache_data)
    return cache_data

# --- Todo List Operations ---

def manage_todo(action, args):
    todos = load_json_file(TODO_FILE, [])
    
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

def clean_len(s):
    return len(ANSI_ESCAPE.sub('', s))

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
    
    # Check if cache is older than 15 mins or missing
    cache_age = time.time() - cache.get("timestamp", 0)
    if cache_age > 900 or not os.path.exists(CACHE_FILE):
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

    # 4. Git Repository Alerts
    if sec.get("git_status"):
        git_data = cache.get("git_status", {})
        if git_data:
            print(make_border_top("Git Repository Tracker", colors))
            clean_count = 0
            shown_any = False
            for repo, rstatus in git_data.items():
                if rstatus:
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
        todos = load_json_file(TODO_FILE, [])
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
