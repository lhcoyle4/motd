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
        "dev_tips": True
    }
}

DEV_TIPS = [
    "Tip: Use Ctrl+Alt+/ to launch the Antigravity CLI anywhere on your system.",
    "Tip: Alt+Left-Click + Drag anywhere inside a window to move it with Alt-Drag.",
    "Tip: Alt+Right-Click + Drag anywhere inside a window to resize it.",
    "Tip: git status -sb is a great way to see a concise branch status with tracking info.",
    "Tip: In PowerShell, you can use Get-Command to quickly find executable locations.",
    "GIS Tip: WGS84 (EPSG:4326) uses degrees, while Web Mercator (EPSG:3857) uses meters.",
    "GIS Tip: SNAP is excellent for historical remote sensing analysis of SAR and optical data.",
    "Developer Tip: Write tests before you write code. It saves time in the long run.",
    "Quote: 'Simplicity is the ultimate sophistication.' — Leonardo da Vinci",
    "Quote: 'Talk is cheap. Show me the code.' — Linus Torvalds"
]

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # Merge missing keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
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
    
    cache_data = {
        "timestamp": time.time(),
        "weather": weather,
        "git_status": git_status
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
        todos.append({"text": task_text, "done": False, "created_at": time.time()})
        save_json_file(TODO_FILE, todos)
        print(f"Added task: '{task_text}'")
        
    elif action == "list":
        if not todos:
            print("No tasks in your todo list.")
            return
        print(f"\n{Fore.CYAN}--- TODO LIST ---{Style.RESET_ALL}")
        for idx, todo in enumerate(todos, 1):
            status = "[x]" if todo["done"] else "[ ]"
            color = Fore.GREEN if todo["done"] else Fore.YELLOW
            print(f"{color}{idx}. {status} {todo['text']}{Style.RESET_ALL}")
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

def draw_bar(percent, width=15):
    filled = int(percent / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
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

BOX_WIDTH = 58
INNER_WIDTH = BOX_WIDTH - 2  # 56

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
    
    logo_line_1 = f"{colors['highlight']}▒█▀▀▀█ ▒█▀▀█ ▒█▄░▒█ ▒█▀▀▄ ▒█▀▀▀█ ▒█▀▀▀█ ▒█░░▒█"
    logo_line_2 = f"{colors['highlight']}░▀▀▀▄▄ ▒█▄▄█ ▒█▒█▒█ ▒█░▒█ ▒█░░▒█ ░▀▀▀▄▄ ▒█▄▄▄█"
    logo_line_3 = f"{colors['highlight']}▒█▄▄▄█ ▒█░▒█ ▒█░░▀█ ▒█▄▄▀ ▒█▄▄▄█ ▒█▄▄▄█ ░░▒█░░"
    
    print(format_row(pad_ansi(logo_line_1, INNER_WIDTH, "center"), "", colors))
    print(format_row(pad_ansi(logo_line_2, INNER_WIDTH, "center"), "", colors))
    print(format_row(pad_ansi(logo_line_3, INNER_WIDTH, "center"), "", colors))
    print(format_row("", "", colors))
    
    # Date, User and Uptime
    user_str = f"Welcome, {config.get('username', 'Louie')}!"
    
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
    cache = load_json_file(CACHE_FILE, {"timestamp": 0, "weather": "Fetching...", "git_status": {}})
    
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
        cpu_bar = draw_bar(stats["cpu_pct"])
        ram_bar = draw_bar(stats["ram_pct"])
        disk_bar = draw_bar(stats["disk_pct"])
        
        print(make_border_top("System Health", colors))
        
        cpu_left = f"  {colors['label']}CPU {colors['val']}[{cpu_bar}] {stats['cpu_pct']:>5.1f}%"
        cpu_right = f"{colors['label']}Uptime: {colors['val']}{stats['uptime']}  "
        print(format_row(cpu_left, cpu_right, colors))
        
        ram_left = f"  {colors['label']}RAM {colors['val']}[{ram_bar}] {stats['ram_pct']:>5.1f}%"
        ram_right = f"{colors['val']}({stats['ram_used']:.1f}/{stats['ram_total']:.1f} GB)  "
        print(format_row(ram_left, ram_right, colors))
        
        disk_left = f"  {colors['label']}Disk{colors['val']}[{disk_bar}] {stats['disk_pct']:>5.1f}%"
        disk_right = f"{colors['val']}({stats['disk_used']:.1f}/{stats['disk_total']:.1f} GB)  "
        print(format_row(disk_left, disk_right, colors))
        
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
            # Wrap tip to 43 characters (INNER_WIDTH 56 - 13 characters for label/indent)
            wrapped_lines = textwrap.wrap(tip, width=43)
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
            for repo, rstatus in git_data.items():
                if rstatus:
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
            print(make_border_bottom(colors))

    # 5. Local Todos
    if sec.get("todos"):
        todos = load_json_file(TODO_FILE, [])
        pending = [t for t in todos if not t["done"]]
        
        if pending:
            title = f"Current Todo Checklist ({len(pending)} pending)"
            print(make_border_top(title, colors))
            for idx, todo in enumerate(pending[:5], 1):
                task_str = todo["text"]
                if len(task_str) > 45:
                    task_str = task_str[:42] + "..."
                left = f"  {Fore.YELLOW}{idx}. [ ] {colors['val']}{task_str}"
                print(format_row(left, "", colors))
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
