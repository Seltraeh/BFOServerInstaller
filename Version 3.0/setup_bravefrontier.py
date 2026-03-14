"""
Brave Frontier Offline — Combined Installer
Installs both the server and the patched Windows client from a single launcher.
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, Label, ttk
import os
import subprocess
import urllib.request
import shutil
import datetime
import xml.etree.ElementTree as ET
import threading
import time
import glob
import sys
import zipfile
import configparser
import webbrowser
import json as _json
import re

# ── Server repo options ──────────────────────────────────────────────────────
KNOWN_REPOS = [
    {
        "label": "Seltraeh – feature/missions-and-unit-stats (recommended)",
        "url": "https://github.com/Seltraeh/server.git",
        "branch": "feature/missions-and-unit-stats",
    },
    {
        "label": "Seltraeh – feature/all-handlers",
        "url": "https://github.com/Seltraeh/server.git",
        "branch": "feature/all-handlers",
    },
    {
        "label": "Seltraeh – main",
        "url": "https://github.com/Seltraeh/server.git",
        "branch": None,
    },
    {
        "label": "decompfrontier – official (default branch)",
        "url": "https://github.com/decompfrontier/server",
        "branch": None,
    },
    {
        "label": "Custom URL / branch…",
        "url": None,
        "branch": None,
    },
]
REPO_URL = KNOWN_REPOS[0]["url"]
REPO_BRANCH = KNOWN_REPOS[0]["branch"]

# ── Client constants ─────────────────────────────────────────────────────────
PROXY_REPO_URL   = "https://github.com/decompfrontier/offline-proxy"
APPX_DOWNLOAD_URL = "https://drive.google.com/file/d/1NB64gzQOe-QQx9fY0mkoZiCSfe3WlTYi/view?usp=sharing"
APPX_FILENAME    = "BraveFrontier_2.19.6.0_x86.appx"
LOOPBACK_URL     = "https://telerik-fiddler.s3.amazonaws.com/fiddler/addons/enableloopbackutility.exe"
CERT_NAME        = "MyBraveFrontier"
CERT_FRIENDLY    = "Brave Frontier Dev Cert"
PATCHED_APPX     = "BraveFrontierPatched.appx"
UNPACKED_DIR_NAME = "BraveFrontierAppxClient"

# ── Shared URLs ──────────────────────────────────────────────────────────────
ASSET_URL     = "https://drive.google.com/file/d/1ApVcJISPovYuWEidnkkTJi_NI8sD1Xmx/view"
CMAKE_URL     = "https://cmake.org/download/"
VS_URL        = "https://visualstudio.microsoft.com/downloads/"
CONFIGURE_PRESET = "debug-win64"

# ── Persisted config ─────────────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.getenv("APPDATA"), "BF_combined_setup.ini")

# ── Runtime globals (set after directory is chosen) ──────────────────────────
BASE_DIR        = None
LOG_FILE        = None
VCPKG_ROOT      = None
REPO_BASE_DIR   = None
SERVER_DIR      = None
VCPKG_TOOLCHAIN = None
VCPKG_CACHE     = None
DEPLOY_DIR      = None
GAME_CONTENT_DIR = None
VS_PROJECT      = None


# ── GitHub helpers ───────────────────────────────────────────────────────────

def fetch_github_branches(repo_url):
    """Return list of branch names from a GitHub repo URL, or [] on failure."""
    m = re.search(r'github\.com[:/](.+?/[^/]+?)(?:\.git)?$', repo_url)
    if not m:
        return []
    slug = m.group(1)
    api_url = f"https://api.github.com/repos/{slug}/branches?per_page=100"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "BFInstaller/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode())
        return [b["name"] for b in data]
    except Exception:
        return []


# ── Config helpers ───────────────────────────────────────────────────────────

def load_previous_dir():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8")
        if "Settings" in config and "base_dir" in config["Settings"]:
            return config["Settings"]["base_dir"]
    return None


def save_dir_choice():
    config = configparser.ConfigParser()
    config["Settings"] = {"base_dir": BASE_DIR}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        config.write(f)


def init_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"[{_ts()}] Brave Frontier combined setup started\n")


def _ts():
    return datetime.datetime.now().strftime("%a %m/%d/%Y %H:%M:%S.%f")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main application
# ═══════════════════════════════════════════════════════════════════════════════

class BFInstallerApp:
    """Combined installer: runs server setup then client setup sequentially."""

    def __init__(self, root):
        self.root = root
        self.root.title("Brave Frontier Offline — Combined Installer")
        self.root.geometry("700x560")
        self.root.resizable(False, False)

        # ── Header ──────────────────────────────────────────────────────────
        tk.Label(root, text="Brave Frontier Offline Installer",
                 font=("TkDefaultFont", 14, "bold")).pack(pady=(12, 2))
        tk.Label(root, text="Sets up the server and patched client in one go.",
                 font=("TkDefaultFont", 9), fg="#555555").pack(pady=(0, 8))

        # ── Progress bar ─────────────────────────────────────────────────────
        self.progress = ttk.Progressbar(root, orient="horizontal", length=660, mode="determinate")
        self.progress.pack(padx=20)
        self.progress["maximum"] = 100

        self.phase_label = tk.Label(root, text="", font=("TkDefaultFont", 9, "italic"), fg="#333333")
        self.phase_label.pack(pady=(2, 4))

        # ── Log window ───────────────────────────────────────────────────────
        self.status_text = scrolledtext.ScrolledText(
            root, width=83, height=20, wrap=tk.WORD, state="disabled",
            font=("Consolas", 8)
        )
        self.status_text.pack(padx=10, pady=4)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=8)
        self.start_button = tk.Button(btn_frame, text="Start Setup", width=16,
                                      command=self.start_setup_thread)
        self.start_button.pack(side="left", padx=8)
        self.exit_button = tk.Button(btn_frame, text="Exit", width=10,
                                     command=root.quit, state="disabled")
        self.exit_button.pack(side="left", padx=8)

        self.running = False
        self.vs_dev_cmd = None
        self.vs_install_path = None

    # ── Logging ─────────────────────────────────────────────────────────────

    def log(self, message):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{_ts()}] {message}\n")

    def update_status(self, message, progress=None):
        self.status_text.config(state="normal")
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.config(state="disabled")
        self.status_text.see(tk.END)
        if progress is not None:
            self.progress["value"] = progress
        self.root.update()

    def set_phase(self, label, progress=None):
        self.phase_label.config(text=label)
        if progress is not None:
            self.progress["value"] = progress
        self.root.update()

    # ── Visual Studio detection ──────────────────────────────────────────────

    def find_visual_studio(self):
        if shutil.which("cl"):
            self.log("Visual Studio found via PATH")
            return True

        vswhere_paths = [
            r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe",
            r"C:\Program Files\Microsoft Visual Studio\Installer\vswhere.exe",
        ]
        vswhere_exe = next((p for p in vswhere_paths if os.path.exists(p)), None)
        if vswhere_exe:
            self.log(f"Found vswhere.exe at {vswhere_exe}")
            result = subprocess.run(
                [vswhere_exe, "-latest",
                 "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                 "-property", "installationPath"],
                capture_output=True, text=True
            )
            vs_path = result.stdout.strip()
            self.log(f"vswhere output: '{vs_path}'")
            if vs_path and os.path.exists(vs_path):
                return self._configure_vs_path(vs_path)
            # Warn if VS present but missing C++ tools
            result2 = subprocess.run(
                [vswhere_exe, "-latest", "-property", "installationPath"],
                capture_output=True, text=True
            )
            vs_path_any = result2.stdout.strip()
            if vs_path_any and os.path.exists(vs_path_any):
                self.log(f"VS found at {vs_path_any} but C++ tools missing")
                messagebox.showwarning(
                    "C++ Tools Missing",
                    f"Visual Studio was found at:\n{vs_path_any}\n\n"
                    "The C++ build tools do not appear to be installed.\n\n"
                    "Please open the Visual Studio Installer, click 'Modify', and ensure\n"
                    "'Desktop development with C++' is checked, then click Modify/Install."
                )
                return False

        # Fallback: scan common install paths
        self.log("vswhere not found or returned nothing — scanning common paths")
        candidate_roots = [
            r"C:\Program Files\Microsoft Visual Studio",
            r"C:\Program Files (x86)\Microsoft Visual Studio",
        ]
        vs_paths = []
        for root_dir in candidate_roots:
            if os.path.exists(root_dir):
                for year in os.listdir(root_dir):
                    for edition in ("Community", "Professional", "Enterprise", "BuildTools"):
                        p = os.path.join(root_dir, year, edition)
                        if os.path.exists(p):
                            vs_paths.append(p)
        vs_paths.insert(0, os.path.join(BASE_DIR, "vcpkg", "installed",
                                         "x64-windows", "tools", "msvc"))
        for vsp in vs_paths:
            if self._configure_vs_path(vsp):
                return True

        self.log("Visual Studio not found in any known location")
        return False

    def _configure_vs_path(self, vs_path):
        msvc_path = os.path.join(vs_path, "VC", "Tools", "MSVC")
        if os.path.exists(msvc_path):
            msvc_versions = glob.glob(os.path.join(msvc_path, "*"))
            if msvc_versions:
                latest = max(msvc_versions, key=os.path.getmtime)
                cl_path = os.path.join(latest, "bin", "Hostx64", "x64", "cl.exe")
                if os.path.exists(cl_path):
                    self.log(f"Visual Studio found at {vs_path}")
                    os.environ["PATH"] += os.pathsep + os.path.dirname(cl_path)
                    vs_dev_cmd_path = os.path.join(vs_path, "Common7", "Tools", "VsDevCmd.bat")
                    if os.path.exists(vs_dev_cmd_path):
                        self.vs_dev_cmd = vs_dev_cmd_path
                        self.log(f"VsDevCmd.bat found at {vs_dev_cmd_path}")
                    self.vs_install_path = vs_path
                    return True
        return False

    def get_cmake_generator(self):
        VS_GENERATOR_MAP = {
            "18": "Visual Studio 18 2026",
            "17": "Visual Studio 17 2022",
            "16": "Visual Studio 16 2019",
        }
        if self.vs_install_path:
            parts = self.vs_install_path.replace("\\", "/").split("/")
            for part in reversed(parts):
                if part in VS_GENERATOR_MAP:
                    gen = VS_GENERATOR_MAP[part]
                    self.log(f"Detected CMake generator: {gen}")
                    return gen
                if part.startswith("20") and len(part) == 4:
                    gen = f"Visual Studio 17 {part}"
                    self.log(f"Detected CMake generator (year-based): {gen}")
                    return gen
        self.log("Could not detect VS version; falling back to VS 17 2022")
        return "Visual Studio 17 2022"

    def run_in_vs_env(self, command):
        if self.vs_dev_cmd:
            cmd = f'cmd /c ""{self.vs_dev_cmd}" && cd /d "{os.getcwd()}" && {" ".join(command)}"'
            return subprocess.run(cmd, capture_output=True, text=True, shell=True, check=False)
        return subprocess.run(command, capture_output=True, text=True, check=False)

    # ── Windows SDK tool helpers (client) ────────────────────────────────────

    def find_sdk_tool(self, tool_name):
        found = shutil.which(tool_name)
        if found:
            self.log(f"{tool_name} found on PATH: {found}")
            return found
        sdk_roots = [
            r"C:\Program Files (x86)\Windows Kits\10\bin",
            r"C:\Program Files\Windows Kits\10\bin",
        ]
        arch_preference = ["x86", "x64"] if "makeappx" in tool_name.lower() else ["x64", "x86"]
        for sdk_root in sdk_roots:
            if not os.path.exists(sdk_root):
                continue
            versions = sorted(
                [d for d in os.listdir(sdk_root) if os.path.isdir(os.path.join(sdk_root, d))],
                reverse=True
            )
            for ver in versions:
                for arch in arch_preference:
                    candidate = os.path.join(sdk_root, ver, arch, tool_name)
                    if os.path.exists(candidate):
                        self.log(f"{tool_name} found at {candidate}")
                        return candidate
        self.log(f"WARNING: {tool_name} not found in Windows Kits or PATH")
        return None

    def run_sdk_tool(self, tool_name, args):
        exe = self.find_sdk_tool(tool_name)
        if not exe:
            raise RuntimeError(
                f"{tool_name} could not be found.\n"
                "Ensure the Windows 10/11 SDK is installed via the Visual Studio Installer\n"
                "(Modify → Individual Components → Windows 10/11 SDK)."
            )
        cmd = [exe] + args
        self.log(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    # ── Dialogs ──────────────────────────────────────────────────────────────

    def prompt_repo_selection(self):
        """Modal: pick server repo/branch. Returns True if confirmed."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Server Repository")
        dialog.geometry("560x420")
        dialog.resizable(False, False)
        dialog.grab_set()

        tk.Label(dialog, text="Choose which server repository to install:",
                 font=("TkDefaultFont", 10, "bold")).pack(pady=(14, 4))

        selected_idx = tk.IntVar(value=0)
        for i, repo in enumerate(KNOWN_REPOS):
            tk.Radiobutton(dialog, text=repo["label"], variable=selected_idx,
                           value=i, anchor="w").pack(fill="x", padx=20)

        custom_frame = tk.Frame(dialog)
        tk.Label(custom_frame, text="Repository URL:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        custom_url_var = tk.StringVar()
        tk.Entry(custom_frame, textvariable=custom_url_var, width=36).grid(row=0, column=1, sticky="w")
        tk.Label(custom_frame, text="Branch (leave blank for default):").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        custom_branch_var = tk.StringVar()
        tk.Entry(custom_frame, textvariable=custom_branch_var, width=36).grid(row=1, column=1, sticky="w")

        def on_radio_change(*_):
            if selected_idx.get() == len(KNOWN_REPOS) - 1:
                custom_frame.pack(padx=20, pady=4, fill="x")
            else:
                custom_frame.pack_forget()

        selected_idx.trace_add("write", on_radio_change)

        # ── Live branch fetcher ──────────────────────────────────────────────
        ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20, pady=(8, 0))
        tk.Label(dialog, text="Or fetch available branches live from the selected repo:",
                 font=("TkDefaultFont", 9, "italic"), fg="#555555").pack(anchor="w", padx=20, pady=(4, 2))
        fetch_row = tk.Frame(dialog)
        fetch_row.pack(padx=20, pady=(0, 4), fill="x")

        fetched_branch_var = tk.StringVar()
        branch_combo = ttk.Combobox(fetch_row, textvariable=fetched_branch_var,
                                    state="disabled", width=30)
        branch_combo.pack(side="left", padx=(0, 8))

        fetch_btn = tk.Button(fetch_row, text="Fetch Branches")
        fetch_btn.pack(side="left")

        def do_fetch():
            idx = selected_idx.get()
            if idx == len(KNOWN_REPOS) - 1:
                url = custom_url_var.get().strip()
            else:
                url = KNOWN_REPOS[idx]["url"] or ""
            if not url:
                messagebox.showwarning("No URL", "Select a repo first.", parent=dialog)
                return
            fetch_btn.config(state="disabled", text="Fetching…")
            dialog.update()
            branches = fetch_github_branches(url)
            fetch_btn.config(state="normal", text="Fetch Branches")
            if branches:
                branch_combo["values"] = branches
                branch_combo.config(state="readonly")
                # Pre-select the branch that matches the current radio selection
                idx2 = selected_idx.get()
                current = KNOWN_REPOS[idx2].get("branch") if idx2 < len(KNOWN_REPOS) - 1 else None
                if current and current in branches:
                    fetched_branch_var.set(current)
                else:
                    fetched_branch_var.set(branches[0])
            else:
                messagebox.showwarning(
                    "Fetch Failed",
                    "Could not retrieve branches (no network or rate-limited).\n"
                    "You can still use the preset options or enter a custom branch.",
                    parent=dialog,
                )

        fetch_btn.config(command=do_fetch)

        self.repo_confirmed = False

        def on_ok():
            global REPO_URL, REPO_BRANCH
            idx = selected_idx.get()
            if idx == len(KNOWN_REPOS) - 1:
                url = custom_url_var.get().strip()
                branch = custom_branch_var.get().strip() or None
                if not url:
                    messagebox.showwarning("Missing URL", "Please enter a repository URL.", parent=dialog)
                    return
                REPO_URL = url
                REPO_BRANCH = branch
            else:
                REPO_URL = KNOWN_REPOS[idx]["url"]
                REPO_BRANCH = KNOWN_REPOS[idx]["branch"]
            # Live combobox selection overrides the preset branch
            live_branch = fetched_branch_var.get().strip()
            if live_branch:
                REPO_BRANCH = live_branch
            self.repo_confirmed = True
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(side="bottom", pady=10)
        tk.Button(btn_frame, text="OK", width=10, command=on_ok).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", width=10, command=dialog.destroy).pack(side="left", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return getattr(self, "repo_confirmed", False)

    def cert_password_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Certificate Password")
        dialog.geometry("400x180")
        dialog.grab_set()
        dialog.resizable(False, False)
        Label(dialog,
              text="Enter a password for the signing certificate.\nThis is only used locally and can be anything.",
              wraplength=380, justify="left").pack(pady=12, padx=10)
        pw_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=pw_var, show="*", width=35)
        entry.pack(pady=4)
        entry.focus()
        result = {"password": None}

        def on_ok():
            pw = pw_var.get().strip()
            if not pw:
                messagebox.showwarning("Required", "Please enter a password.", parent=dialog)
                return
            result["password"] = pw
            dialog.destroy()

        tk.Button(dialog, text="OK", width=10, command=on_ok).pack(pady=8)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return result["password"]

    def manual_appx_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Download APPX Manually")
        dialog.geometry("540x280")
        dialog.grab_set()
        Label(dialog, text=(
            "The APPX file needs to be downloaded manually.\n\n"
            "1. Click the link below to open Google Drive.\n"
            "2. Download the file and save it as:\n"
            f"   {os.path.join(BASE_DIR, APPX_FILENAME)}\n\n"
            "Once the file is in place, click OK to continue."
        ), wraplength=510, justify="left").pack(pady=10, padx=10)
        link = Label(dialog, text=APPX_DOWNLOAD_URL, fg="blue", cursor="hand2")
        link.pack(pady=4)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(APPX_DOWNLOAD_URL))
        tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.wait_window(dialog)

    def manual_asset_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Asset Setup")
        dialog.geometry("520x320")
        dialog.grab_set()
        Label(dialog, text=(
            "Automatic download is not available. Please manually download and place the assets:\n\n"
            "1. Download 21900.zip from the link below.\n"
            "2. Extract 21900.zip, then extract assets.zip inside it.\n"
            "3. Copy the 'content' and 'mst' folders to:\n"
            f"   {GAME_CONTENT_DIR}\n\n"
            "Once done, click OK to continue."
        ), wraplength=500, justify="left").pack(pady=10, padx=10)
        link = Label(dialog, text=ASSET_URL, fg="blue", cursor="hand2")
        link.pack(pady=4)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(ASSET_URL))
        tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.wait_window(dialog)

    def cmake_install_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Install CMake")
        dialog.geometry("520x220")
        dialog.grab_set()
        Label(dialog, text=(
            "CMake is not installed.\n\n"
            "1. Click the link below to open the download page.\n"
            "2. Download the latest Windows installer.\n"
            "3. Run it and select 'Add CMake to the system PATH for all users'.\n"
            "4. Once installed, close this program and relaunch it."
        ), wraplength=500, justify="left").pack(pady=10, padx=10)
        link = Label(dialog, text=CMAKE_URL, fg="blue", cursor="hand2")
        link.pack(pady=4)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(CMAKE_URL))
        tk.Button(dialog, text="Close Tutorial", command=dialog.destroy).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.wait_window(dialog)

    def vs_install_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Install Visual Studio")
        dialog.geometry("520x320")
        dialog.grab_set()
        Label(dialog, text=(
            "Visual Studio with C++ tools was not detected.\n\n"
            "1. Click the link below to open the download page.\n"
            "2. Download Visual Studio Community (it's free).\n"
            "3. Run the installer and select 'Desktop development with C++'.\n"
            "4. Ensure 'Windows 11 SDK' and the MSVC build tools are checked.\n"
            "5. Install (may require ~10+ GB of space).\n"
            "6. Once installed, click OK to continue."
        ), wraplength=500, justify="left").pack(pady=10, padx=10)
        link = Label(dialog, text=VS_URL, fg="blue", cursor="hand2")
        link.pack(pady=4)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(VS_URL))
        tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.wait_window(dialog)

    def find_cmakelists(self, start_dir):
        for root, dirs, files in os.walk(start_dir):
            if "CMakeLists.txt" in files:
                return root
        return None

    # ── Entry point ──────────────────────────────────────────────────────────

    def start_setup_thread(self):
        if self.running:
            return

        # Pick server repo first
        if not self.prompt_repo_selection():
            return

        self.running = True
        self.start_button.config(state="disabled")

        global BASE_DIR, LOG_FILE, VCPKG_ROOT, REPO_BASE_DIR, SERVER_DIR
        global VCPKG_TOOLCHAIN, VCPKG_CACHE, DEPLOY_DIR, GAME_CONTENT_DIR, VS_PROJECT

        default_dir = os.path.join(os.getenv("USERPROFILE"), "BF")
        previous_dir = load_previous_dir()
        if previous_dir and os.path.exists(previous_dir):
            BASE_DIR = previous_dir
        else:
            dir_path = filedialog.asksaveasfilename(
                title="Select or Create Root Directory",
                initialdir=os.path.dirname(default_dir),
                initialfile=os.path.basename(default_dir),
                filetypes=[("Directory", "*")],
                defaultextension=""
            )
            if not dir_path or dir_path == default_dir:
                dir_path = default_dir
            BASE_DIR = os.path.abspath(dir_path)
            os.makedirs(BASE_DIR, exist_ok=True)
            save_dir_choice()
            messagebox.showinfo("Directory Confirmation",
                f"Root directory set to {BASE_DIR}.\nClick OK to proceed.")

        # Derive all paths from BASE_DIR
        VCPKG_ROOT      = os.path.join(BASE_DIR, "vcpkg")
        REPO_BASE_DIR   = os.path.join(BASE_DIR, "BF-WorkingDir", "server")
        SERVER_DIR      = os.path.join(REPO_BASE_DIR, "server")
        VCPKG_TOOLCHAIN = os.path.join(VCPKG_ROOT, "scripts", "buildsystems", "vcpkg.cmake")
        VCPKG_CACHE     = os.path.join(VCPKG_ROOT, "downloads")
        DEPLOY_DIR      = os.path.join(SERVER_DIR, "deploy")
        GAME_CONTENT_DIR = os.path.join(DEPLOY_DIR, "game_content")
        VS_PROJECT      = os.path.join(SERVER_DIR, "standalone_frontend", "gimuserverw.vcxproj")
        LOG_FILE        = os.path.join(BASE_DIR, "bf_combined_setup.log")
        init_log()
        self.log(f"Root directory: {BASE_DIR}")

        threading.Thread(target=self.run_all, daemon=True).start()

    # ════════════════════════════════════════════════════════════════════════
    #  PHASE 1 — SERVER SETUP
    # ════════════════════════════════════════════════════════════════════════

    def run_all(self):
        try:
            self.run_server_setup()
            self.run_client_setup()
        except Exception as e:
            self.log(f"Fatal error: {e}")
            messagebox.showerror("Error",
                f"An error occurred:\n{e}\n\nSee {LOG_FILE} for details.")
            self.exit_button.config(state="normal")
        finally:
            self.running = False

    def run_server_setup(self):
        global SERVER_DIR, DEPLOY_DIR, GAME_CONTENT_DIR, VS_PROJECT

        self.set_phase("Phase 1 of 2 — Server Setup", progress=0)
        self.update_status("=" * 70)
        self.update_status("  PHASE 1: SERVER SETUP")
        self.update_status("=" * 70)

        # ── S1: Git ──────────────────────────────────────────────────────────
        self.update_status("\n[S1/10] Checking for Git...")
        if not shutil.which("git"):
            self.log("Git not found")
            messagebox.showinfo("Install Git",
                "Git is not installed.\n\n"
                "1. Go to https://git-scm.com/download/win\n"
                "2. Download and run the installer (default options are fine).\n"
                "3. Click OK once done.")
            self.update_status("Waiting for Git installation...")
            while not shutil.which("git"):
                time.sleep(1)
        self.log("Git found")
        self.update_status("Git is installed.")
        self.progress["value"] = 3

        # ── S2: CMake ────────────────────────────────────────────────────────
        self.update_status("[S2/10] Checking for CMake...")
        if not shutil.which("cmake"):
            self.log("CMake not found")
            self.cmake_install_prompt()
            self.update_status("Waiting for CMake installation and restart...")
            return  # User must relaunch after installing CMake
        self.log("CMake found")
        self.update_status("CMake is installed.")
        self.progress["value"] = 5

        # ── S3: Visual Studio ────────────────────────────────────────────────
        self.update_status("[S3/10] Checking for Visual Studio...")
        if not self.find_visual_studio():
            self.log("Visual Studio (cl.exe) not found")
            self.vs_install_prompt()
            self.update_status("Waiting for Visual Studio installation...")
            while not self.find_visual_studio():
                time.sleep(1)
        self.log("Visual Studio found")
        self.update_status("Visual Studio is installed.")
        self.progress["value"] = 7

        # ── S4: PowerShell ───────────────────────────────────────────────────
        self.update_status("[S4/10] Checking for PowerShell...")
        if not shutil.which("powershell"):
            messagebox.showerror("Error", "PowerShell is required but was not found.")
            self.exit_button.config(state="normal")
            raise RuntimeError("PowerShell not found.")
        self.log("PowerShell found")
        self.update_status("All server prerequisites satisfied.")
        self.progress["value"] = 8

        # ── S5: Directories ──────────────────────────────────────────────────
        self.update_status("[S5/10] Setting up directories...")
        os.makedirs(BASE_DIR, exist_ok=True)
        self.log(f"Directories set up at {BASE_DIR}")
        self.update_status("Directories are set up.")
        self.progress["value"] = 9

        # ── S6: Clone / sync server repo ────────────────────────────────────
        self.update_status("[S6/10] Downloading server code...")
        if os.path.exists(REPO_BASE_DIR):
            self.update_status("Syncing server repository...")
            os.chdir(REPO_BASE_DIR)
            if REPO_BRANCH:
                # Fetch then hard-reset to the desired branch (works with shallow clones)
                subprocess.run(
                    ["git", "fetch", "--depth=1", "origin", REPO_BRANCH],
                    capture_output=True, text=True,
                )
                result = subprocess.run(
                    ["git", "checkout", "-B", REPO_BRANCH, f"origin/{REPO_BRANCH}"],
                    capture_output=True, text=True,
                )
                self.log(f"git checkout stdout: {result.stdout}")
                self.log(f"git checkout stderr: {result.stderr}")
            else:
                result = subprocess.run(["git", "pull"], capture_output=True, text=True)
                self.log(f"git pull stdout: {result.stdout}")
                self.log(f"git pull stderr: {result.stderr}")
            result.check_returncode()
        else:
            self.update_status("Cloning server repository...")
            clone_cmd = ["git", "clone", "--depth=1"]
            if REPO_BRANCH:
                clone_cmd += ["--branch", REPO_BRANCH]
            clone_cmd += [REPO_URL, REPO_BASE_DIR]
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            self.log(f"git clone stdout: {result.stdout}")
            self.log(f"git clone stderr: {result.stderr}")
            result.check_returncode()

        # Ensure deploy/ is in .gitignore
        gitignore_path = os.path.join(REPO_BASE_DIR, ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "deploy/" not in content:
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write("\ndeploy/")
                self.log("Added deploy/ to .gitignore")

        # Patch CMakePresets.json generator
        cmake_presets_path = os.path.join(REPO_BASE_DIR, "CMakePresets.json")
        correct_generator = self.get_cmake_generator()
        if os.path.exists(cmake_presets_path):
            with open(cmake_presets_path, "r", encoding="utf-8") as f:
                presets_data = _json.load(f)
            patched = False
            for preset in presets_data.get("configurePresets", []):
                current_gen = preset.get("generator", "")
                if current_gen.startswith("Visual Studio") and current_gen != correct_generator:
                    self.log(f"Patching CMakePresets.json: '{current_gen}' -> '{correct_generator}'")
                    preset["generator"] = correct_generator
                    patched = True
            if patched:
                with open(cmake_presets_path, "w", encoding="utf-8") as f:
                    _json.dump(presets_data, f, indent=2)
                self.log("CMakePresets.json patched")
                self.update_status(f"Patched CMakePresets.json to use {correct_generator}.")

        self.update_status("Server code downloaded.")
        self.progress["value"] = 15

        # ── S7: vcpkg ────────────────────────────────────────────────────────
        self.update_status("[S7/10] Setting up vcpkg (library manager)...")
        if "VCPKG_ROOT" in os.environ:
            del os.environ["VCPKG_ROOT"]
        os.environ["VCPKG_DEFAULT_BINARY_CACHE"] = VCPKG_CACHE
        if not os.path.exists(VCPKG_ROOT):
            self.update_status("Downloading vcpkg...")
            result = subprocess.run(
                ["git", "clone", "https://github.com/microsoft/vcpkg.git", VCPKG_ROOT],
                capture_output=True, text=True
            )
            self.log(f"vcpkg clone stdout: {result.stdout}")
            result.check_returncode()
            self.update_status("Bootstrapping vcpkg...")
            result = subprocess.run(
                [os.path.join(VCPKG_ROOT, "bootstrap-vcpkg.bat"), "-disableMetrics"],
                capture_output=True, text=True
            )
            self.log(f"vcpkg bootstrap stdout: {result.stdout}")
            result.check_returncode()
        else:
            self.update_status("vcpkg already set up.")
        self.update_status("Integrating vcpkg...")
        result = subprocess.run(
            [os.path.join(VCPKG_ROOT, "vcpkg.exe"), "integrate", "install"],
            capture_output=True, text=True
        )
        self.log(f"vcpkg integrate stdout: {result.stdout}")
        result.check_returncode()
        self.update_status("vcpkg set up.")
        self.progress["value"] = 20

        # ── S8: Install dependencies ─────────────────────────────────────────
        self.update_status("[S8/10] Installing required libraries (~16 min, please wait)...")
        os.chdir(REPO_BASE_DIR)
        result = subprocess.run(
            [os.path.join(VCPKG_ROOT, "vcpkg.exe"), "install"],
            capture_output=True, text=True
        )
        self.log(f"vcpkg install stdout: {result.stdout}")
        self.log(f"vcpkg install stderr: {result.stderr}")
        result.check_returncode()
        self.update_status("Libraries installed.")
        self.progress["value"] = 32

        # ── S9: Verify server dir, configure, build ──────────────────────────
        self.update_status("[S9/10] Configuring the server (~10 min, please wait)...")

        # Locate CMakeLists.txt
        if not os.path.exists(os.path.join(SERVER_DIR, "CMakeLists.txt")):
            cmakelists_dir = self.find_cmakelists(REPO_BASE_DIR)
            if cmakelists_dir:
                SERVER_DIR   = cmakelists_dir
                DEPLOY_DIR   = os.path.join(SERVER_DIR, "deploy")
                GAME_CONTENT_DIR = os.path.join(DEPLOY_DIR, "game_content")
                VS_PROJECT   = os.path.join(SERVER_DIR, "standalone_frontend", "gimuserverw.vcxproj")
            else:
                raise RuntimeError(f"Missing CMakeLists.txt in {REPO_BASE_DIR}")
        if not os.path.exists(os.path.join(SERVER_DIR, "CMakePresets.json")):
            raise RuntimeError(f"Missing CMakePresets.json in {SERVER_DIR}")

        os.chdir(SERVER_DIR)
        # Clear stale cmake cache
        for cache_root in [SERVER_DIR, REPO_BASE_DIR]:
            for stale in ["CMakeCache.txt"]:
                sp = os.path.join(cache_root, stale)
                if os.path.exists(sp):
                    os.remove(sp)
            stale_dir = os.path.join(cache_root, "CMakeFiles")
            if os.path.exists(stale_dir):
                shutil.rmtree(stale_dir)

        result = self.run_in_vs_env(["cmake", "--preset", CONFIGURE_PRESET])
        self.log(f"cmake configure stdout: {result.stdout}")
        self.log(f"cmake configure stderr: {result.stderr}")
        result.check_returncode()
        if not os.path.exists(VS_PROJECT):
            result = self.run_in_vs_env(["cmake", "--preset", CONFIGURE_PRESET])
            self.log(f"re-cmake stdout: {result.stdout}")
            result.check_returncode()
        self.update_status("Server configured.")

        self.update_status("Building the server...")
        result = self.run_in_vs_env(["cmake", "--build", ".", "--config", "Debug", "--verbose"])
        self.log(f"cmake build stdout: {result.stdout}")
        self.log(f"cmake build stderr: {result.stderr}")
        result.check_returncode()
        self.update_status("Server built successfully.")
        self.progress["value"] = 44

        # ── S10: Assets, config, VS project ─────────────────────────────────
        self.update_status("[S10/10] Setting up game assets and configuration...")
        os.makedirs(DEPLOY_DIR, exist_ok=True)
        os.makedirs(GAME_CONTENT_DIR, exist_ok=True)

        if not os.path.exists(os.path.join(GAME_CONTENT_DIR, "content")):
            self.manual_asset_prompt()
            while (not os.path.exists(os.path.join(GAME_CONTENT_DIR, "content")) or
                   not os.path.exists(os.path.join(GAME_CONTENT_DIR, "mst"))):
                time.sleep(1)
        else:
            self.update_status("Assets already present.")

        config_json = os.path.join(DEPLOY_DIR, "config.json")
        if not os.path.exists(config_json):
            sample = os.path.join(SERVER_DIR, "config-sample.json")
            if os.path.exists(sample):
                shutil.copy(sample, config_json)
            with open(config_json, "w", encoding="utf-8") as f:
                f.write('{\n'
                        '  "database_host": "localhost",\n'
                        '  "database_port": 3306,\n'
                        '  "database_user": "your_username",\n'
                        '  "database_password": "your_password",\n'
                        '  "database_name": "bravefrontier_db"\n'
                        '}')
            self.log("Copied and prefilled config.json")

        # Set VS project working directory
        if os.path.exists(VS_PROJECT):
            ET.register_namespace("", "http://schemas.microsoft.com/developer/msbuild/2003")
            tree = ET.parse(VS_PROJECT)
            root = tree.getroot()
            for pg in root.findall(".//{http://schemas.microsoft.com/developer/msbuild/2003}PropertyGroup[@Condition]"):
                wd = ET.SubElement(pg, "{http://schemas.microsoft.com/developer/msbuild/2003}WorkingDirectory")
                wd.text = DEPLOY_DIR
            tree.write(VS_PROJECT, encoding="utf-8", xml_declaration=False)
            self.log("VS project WorkingDirectory set")

        self.update_status("Game assets set up.")
        self.progress["value"] = 50

        self.update_status("\n✓ SERVER SETUP COMPLETE\n")
        messagebox.showinfo("Server Ready",
            "The server has been built and configured.\n\n"
            f"Click OK to open config.json — edit your credentials (or leave them for SQLite offline), save, and close Notepad.\n\n"
            f"File: {config_json}")
        subprocess.run(["notepad", config_json])
        self.log("config.json opened in Notepad")

    # ════════════════════════════════════════════════════════════════════════
    #  PHASE 2 — CLIENT SETUP
    # ════════════════════════════════════════════════════════════════════════

    def run_client_setup(self):
        self.set_phase("Phase 2 of 2 — Client Setup", progress=50)
        self.update_status("=" * 70)
        self.update_status("  PHASE 2: CLIENT SETUP")
        self.update_status("=" * 70)

        # ── C1: Prerequisites ────────────────────────────────────────────────
        self.update_status("\n[C1/9] Checking prerequisites...")

        if not shutil.which("git"):
            messagebox.showinfo("Install Git",
                "Git is not installed.\n\n"
                "1. Go to https://git-scm.com/download/win\n"
                "2. Download and run the installer (default options are fine).\n"
                "3. Click OK once done.")
            self.update_status("Waiting for Git installation...")
            while not shutil.which("git"):
                time.sleep(2)
        self.update_status("Git is installed.")

        if not shutil.which("cmake"):
            messagebox.showinfo("Install CMake",
                "CMake is not installed.\n\n"
                "1. Go to https://cmake.org/download/\n"
                "2. Download the Windows installer and select 'Add CMake to PATH'.\n"
                "3. Restart this installer after CMake is installed.")
            self.exit_button.config(state="normal")
            raise RuntimeError("CMake not found — restart installer after installing CMake.")

        if not self.find_visual_studio():
            messagebox.showerror("Visual Studio Required",
                "Visual Studio with C++ tools was not detected.\n"
                "Please install Visual Studio with 'Desktop development with C++' workload,\n"
                "then relaunch this installer.")
            self.exit_button.config(state="normal")
            raise RuntimeError("Visual Studio not found.")

        if not shutil.which("powershell"):
            messagebox.showerror("Error", "PowerShell is required but was not found.")
            self.exit_button.config(state="normal")
            raise RuntimeError("PowerShell not found.")

        self.update_status("All client prerequisites satisfied.")
        self.progress["value"] = 53

        # ── C2: Certificate password ─────────────────────────────────────────
        self.update_status("[C2/9] Certificate setup...")
        cert_password = self.cert_password_prompt()
        if not cert_password:
            self.update_status("Client setup cancelled.")
            self.exit_button.config(state="normal")
            raise RuntimeError("Certificate password not provided — setup cancelled.")

        # ── C3: Clone / update offline-proxy ────────────────────────────────
        self.update_status("[C3/9] Downloading the offline proxy...")
        proxy_dir = os.path.join(BASE_DIR, "offline-proxy")
        if os.path.exists(proxy_dir):
            self.update_status("Syncing offline-proxy repository...")
            os.chdir(proxy_dir)
            result = subprocess.run(["git", "pull"], capture_output=True, text=True)
            self.log(f"git pull stdout: {result.stdout}")
            result.check_returncode()
        else:
            self.update_status("Cloning offline-proxy repository...")
            result = subprocess.run(
                ["git", "clone", "--depth=1", PROXY_REPO_URL, proxy_dir],
                capture_output=True, text=True
            )
            self.log(f"git clone stdout: {result.stdout}")
            result.check_returncode()
        self.update_status("Proxy repository ready.")
        self.progress["value"] = 58

        # ── C4: Build proxy ──────────────────────────────────────────────────
        self.update_status("[C4/9] Building offline proxy (Win32 Debug)...")
        os.chdir(proxy_dir)

        # Patch CMakePresets.json if needed
        cmake_presets_path = os.path.join(proxy_dir, "CMakePresets.json")
        if os.path.exists(cmake_presets_path):
            correct_generator = self.get_cmake_generator()
            with open(cmake_presets_path, "r", encoding="utf-8") as f:
                presets_data = _json.load(f)
            patched = False
            for preset in presets_data.get("configurePresets", []):
                current_gen = preset.get("generator", "")
                if current_gen.startswith("Visual Studio") and current_gen != correct_generator:
                    self.log(f"Patching proxy preset '{preset.get('name')}': '{current_gen}' -> '{correct_generator}'")
                    preset["generator"] = correct_generator
                    patched = True
            if patched:
                with open(cmake_presets_path, "w", encoding="utf-8") as f:
                    _json.dump(presets_data, f, indent=2)

        # Clear stale cache
        for stale in ["CMakeCache.txt"]:
            sp = os.path.join(proxy_dir, stale)
            if os.path.exists(sp):
                os.remove(sp)
        cmake_files = os.path.join(proxy_dir, "CMakeFiles")
        if os.path.exists(cmake_files):
            shutil.rmtree(cmake_files)

        # Configure
        result = self.run_in_vs_env(["cmake", "--preset", "debug-vs"])
        self.log(f"cmake configure stdout: {result.stdout}")
        self.log(f"cmake configure stderr: {result.stderr}")
        if result.returncode != 0:
            self.log("Preset configure failed; retrying with explicit Win32 flags")
            gen = self.get_cmake_generator()
            build_dir = os.path.join(proxy_dir, "build_debug")
            result = self.run_in_vs_env([
                "cmake", "-G", gen, "-A", "Win32", "-B", build_dir, "-DCMAKE_BUILD_TYPE=Debug"
            ])
            self.log(f"cmake fallback configure stdout: {result.stdout}")
            result.check_returncode()
        else:
            build_dir = proxy_dir

        result = self.run_in_vs_env(["cmake", "--build", build_dir, "--config", "Debug"])
        self.log(f"cmake build stdout: {result.stdout}")
        self.log(f"cmake build stderr: {result.stderr}")
        result.check_returncode()
        self.update_status("Proxy built successfully.")

        # Locate libcurl.dll
        libcurl_candidates = glob.glob(os.path.join(proxy_dir, "**", "libcurl.dll"), recursive=True)
        debug_candidates = [p for p in libcurl_candidates if "Debug" in p]
        libcurl_path = debug_candidates[0] if debug_candidates else (libcurl_candidates[0] if libcurl_candidates else None)
        if not libcurl_path or not os.path.exists(libcurl_path):
            raise RuntimeError(
                "libcurl.dll was not found after building the proxy.\n"
                f"Searched in: {proxy_dir}\n"
                "Please build offline-proxy manually in Visual Studio (Win32, Debug),\n"
                "then re-run this installer."
            )
        self.update_status("Found libcurl.dll.")
        self.progress["value"] = 66

        # ── C5: APPX ─────────────────────────────────────────────────────────
        self.update_status("[C5/9] Checking for APPX file...")
        appx_path = os.path.join(BASE_DIR, APPX_FILENAME)
        if not os.path.exists(appx_path):
            self.manual_appx_prompt()
            timeout, elapsed = 600, 0
            while not os.path.exists(appx_path):
                time.sleep(2)
                elapsed += 2
                if elapsed >= timeout:
                    raise RuntimeError("APPX file not found after waiting. Please re-run the installer.")
        self.update_status("APPX file is present.")
        self.progress["value"] = 70

        # ── C6: Unpack, patch, repack ────────────────────────────────────────
        self.update_status("[C6/9] Unpacking and patching the client...")

        makeappx_exe = self.find_sdk_tool("makeappx.exe")
        if not makeappx_exe:
            raise RuntimeError(
                "makeappx.exe could not be found in the Windows SDK.\n\n"
                "Please open the Visual Studio Installer, click 'Modify', go to\n"
                "'Individual Components', and ensure a Windows SDK is checked."
            )

        unpacked_dir = os.path.join(BASE_DIR, UNPACKED_DIR_NAME)
        if os.path.isfile(unpacked_dir):
            os.remove(unpacked_dir)
        elif os.path.isdir(unpacked_dir):
            shutil.rmtree(unpacked_dir)

        result = self.run_sdk_tool("makeappx.exe", ["unpack", "/p", appx_path, "/d", unpacked_dir, "/nv"])
        self.log(f"makeappx unpack stdout: {result.stdout}")
        if result.returncode != 0:
            raise RuntimeError(f"makeappx unpack failed:\n{result.stderr.strip()}")
        if not os.path.isdir(unpacked_dir):
            raise RuntimeError(f"makeappx succeeded but {unpacked_dir} was not created.")

        # Copy libcurl.dll
        shutil.copy2(libcurl_path, unpacked_dir)

        # Remove files that must not be repacked
        for item in ["AppxMetadata", "AppxSignature.p7x", "AppxBlockMap.xml", "ApplicationInsights.config"]:
            target = os.path.join(unpacked_dir, item)
            if os.path.exists(target):
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)

        # Patch AppxManifest.xml Publisher
        manifest_path = os.path.join(unpacked_dir, "AppxManifest.xml")
        if not os.path.exists(manifest_path):
            raise RuntimeError(f"AppxManifest.xml not found in {unpacked_dir}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
        patched_manifest = re.sub(
            r'(<Identity\b[^>]*?\bPublisher=")[^"]*(")',
            rf'\1CN={CERT_NAME}\2',
            manifest_text
        )
        if patched_manifest == manifest_text:
            self.log("WARNING: Publisher replacement had no effect — check manifest format")
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(patched_manifest)

        self.update_status("Client patched.")
        self.progress["value"] = 76

        # ── C7: Generate & install certificate ──────────────────────────────
        self.update_status("[C7/9] Generating signing certificate...")
        pfx_path = os.path.join(BASE_DIR, "MyKey.pfx")

        # Purge any old certs with this CN
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f'Get-ChildItem Cert:\\CurrentUser\\My | '
             f'Where-Object {{ $_.Subject -eq "CN={CERT_NAME}" }} | '
             f'Remove-Item -Force'],
            capture_output=True, text=True
        )

        cert_script = (
            f'$cert = New-SelfSignedCertificate '
            f'-Type Custom '
            f'-Subject "CN={CERT_NAME}" '
            f'-KeyUsage DigitalSignature '
            f'-FriendlyName "{CERT_FRIENDLY}" '
            f'-CertStoreLocation "Cert:\\CurrentUser\\My" '
            f'-TextExtension @("2.5.29.37={{text}}1.3.6.1.5.5.7.3.3", "2.5.29.19={{text}}"); '
            f'$cert.Thumbprint'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cert_script],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Certificate generation failed:\n{result.stderr.strip()}")
        thumbprint_lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        if not thumbprint_lines:
            raise RuntimeError("Could not extract certificate thumbprint from PowerShell output.")
        thumbprint = thumbprint_lines[-1]
        self.log(f"New certificate thumbprint: {thumbprint}")
        self.update_status("Certificate created.")

        # Export PFX
        export_script = (
            f'$pw = ConvertTo-SecureString -String "{cert_password}" -Force -AsPlainText; '
            f'Export-PfxCertificate -Cert "Cert:\\CurrentUser\\My\\{thumbprint}" '
            f'-FilePath "{pfx_path}" -Password $pw'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", export_script],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"PFX export failed:\n{result.stderr.strip()}")
        self.update_status("Certificate exported.")

        # Install cert to Trusted Root (elevated)
        install_ps1 = os.path.join(BASE_DIR, "_install_cert.ps1")
        install_script = (
            f'$pw = ConvertTo-SecureString -String "{cert_password}" -Force -AsPlainText; '
            f'Import-PfxCertificate -FilePath "{pfx_path}" '
            f'-CertStoreLocation "Cert:\\LocalMachine\\Root" -Password $pw; '
            f'Start-Sleep -Seconds 1'
        )
        with open(install_ps1, "w", encoding="utf-8") as f:
            f.write(install_script)
        try:
            import ctypes
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell.exe",
                f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{install_ps1}"',
                None, 1
            )
            if rc > 32:
                self.log("Elevated cert install launched")
                time.sleep(3)
                self.update_status("Certificate installed to Trusted Root.")
            else:
                raise RuntimeError(f"ShellExecuteW returned {rc}")
        except Exception as elev_err:
            self.log(f"Elevated cert install failed: {elev_err}")
            messagebox.showwarning("Certificate Installation",
                "Could not automatically install the certificate to Trusted Root.\n\n"
                "Please manually install it:\n"
                f"1. Double-click: {pfx_path}\n"
                "2. Select 'Local Machine'\n"
                "3. Choose 'Trusted Root Certification Authorities'\n"
                "4. Click Finish → Yes")
        finally:
            if os.path.exists(install_ps1):
                os.remove(install_ps1)

        self.progress["value"] = 82

        # ── C8: Pack & sign ──────────────────────────────────────────────────
        self.update_status("[C8/9] Packing and signing the patched client...")
        patched_appx_path = os.path.join(BASE_DIR, PATCHED_APPX)
        if os.path.exists(patched_appx_path):
            os.remove(patched_appx_path)

        result = self.run_sdk_tool("makeappx.exe", ["pack", "/d", unpacked_dir, "/p", patched_appx_path, "/nv"])
        if result.returncode != 0:
            raise RuntimeError(f"makeappx pack failed:\n{result.stderr.strip()}")
        self.update_status("APPX packed.")

        result = self.run_sdk_tool("signtool.exe", [
            "sign", "/a", "/v", "/fd", "SHA256",
            "/f", pfx_path, "/p", cert_password, patched_appx_path
        ])
        if result.returncode != 0:
            raise RuntimeError(f"SignTool failed:\n{result.stderr.strip()}")
        self.update_status("APPX signed.")
        self.progress["value"] = 90

        # ── C9: Install + loopback ───────────────────────────────────────────
        self.update_status("[C9/9] Installing the patched client...")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f'Add-AppxPackage "{patched_appx_path}"'],
            capture_output=True, text=True
        )
        self.log(f"Add-AppxPackage stdout: {result.stdout}")
        if result.returncode != 0:
            raise RuntimeError(f"Add-AppxPackage failed:\n{result.stderr.strip()}")
        self.update_status("Patched client installed!")

        # Download loopback utility
        loopback_exe = os.path.join(BASE_DIR, "enableloopbackutility.exe")
        if not os.path.exists(loopback_exe):
            self.update_status("Downloading loopback utility...")
            try:
                urllib.request.urlretrieve(LOOPBACK_URL, loopback_exe)
                self.log(f"Downloaded loopback utility to {loopback_exe}")
            except Exception as e:
                self.log(f"Could not download loopback utility: {e}")
                loopback_exe = None

        self.progress["value"] = 100

        # ── Final summary ────────────────────────────────────────────────────
        self.update_status("\n" + "=" * 70)
        self.update_status("  ✓ ALL DONE! Both server and client are installed.")
        self.update_status("=" * 70)
        self.update_status("\nTo run Brave Frontier offline:")
        self.update_status("\n  1. Enable loopback for the Brave Frontier app:")
        if loopback_exe and os.path.exists(loopback_exe):
            self.update_status(f"     Run: {loopback_exe}")
            self.update_status("     Select 'Brave Frontier', check 'Enable loopback', click Save Changes.")
            messagebox.showinfo("Enable Loopback",
                "Click OK to launch the loopback utility.\n\n"
                "Select 'Brave Frontier', check 'Enable loopback', then click 'Save Changes'.\n\n"
                "A UAC prompt may appear — click Yes to allow it.")
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "runas", loopback_exe, None, None, 1)
            except Exception as e:
                self.log(f"Could not launch loopback utility: {e}")
                self.update_status(f"     Could not auto-launch. Run manually:\n     {loopback_exe}")
        else:
            self.update_status(f"     Download manually: {LOOPBACK_URL}")

        self.update_status(f"\n  2. Open the server project in Visual Studio:")
        self.update_status(f"     Double-click: {VS_PROJECT}")
        self.update_status("     Right-click 'gimuserverw' → Set as Startup Project → press Play.")

        self.update_status("\n  3. Launch 'Brave Frontier' from the Start menu.")
        self.update_status("     A console window should appear alongside the game.\n")
        self.update_status(f"Full log saved to: {LOG_FILE}")

        messagebox.showinfo("Open Visual Studio",
            "Click OK to open the server project in Visual Studio.\n\n"
            "Set 'gimuserverw' as the Startup Project, then click the green Play button.")
        subprocess.run(["start", "", VS_PROJECT], shell=True)

        self.exit_button.config(state="normal")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = BFInstallerApp(root)
    root.mainloop()
