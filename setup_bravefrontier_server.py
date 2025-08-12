import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, Label
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
import zipfile  # Added for zip validation
import configparser  # Added for persisting directory choice
import webbrowser  # For opening hyperlink

# Configuration (to be set by user prompt)
REPO_URL = "https://github.com/decompfrontier/server"  # Define the repository URL
ASSET_URL = "https://drive.google.com/file/d/1ApVcJISPovYuWEidnkkTJi_NI8sD1Xmx/view"
ASSET_ZIP = "21900.zip"
CONFIG_FILE = os.path.join(os.getenv("APPDATA"), "BF_setup.ini")
CONFIGURE_PRESET = "debug-win64"  # Define the CMake preset
TEMP_DIR = os.path.join(os.getenv("TEMP"), "BF_Setup")  # Define temporary directory
CMAKE_URL = "https://cmake.org/download/"
VS_URL = "https://visualstudio.microsoft.com/downloads/"

# Load previous directory if exists
def load_previous_dir():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
        if 'Settings' in config and 'base_dir' in config['Settings']:
            return config['Settings']['base_dir']
    return None

# Save directory choice
def save_dir_choice():
    config = configparser.ConfigParser()
    config['Settings'] = {'base_dir': BASE_DIR}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

# Initialize log file (to be set after BASE_DIR)
def init_log():
    with open(LOG_FILE, "w", encoding='utf-8') as f:
        f.write(f"[{datetime.datetime.now().strftime('%a %m/%d/%Y %H:%M:%S.%f')}] Starting setup\n")

class SetupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Brave Frontier Server Setup")
        self.root.geometry("600x400")
        self.root.resizable(False, False)

        # Status text area
        self.status_text = scrolledtext.ScrolledText(root, width=70, height=15, wrap=tk.WORD, state='disabled')
        self.status_text.pack(padx=10, pady=10)

        # Start button
        self.start_button = tk.Button(root, text="Start Setup", command=self.start_setup_thread)
        self.start_button.pack(pady=5)

        # Exit button (initially disabled)
        self.exit_button = tk.Button(root, text="Exit", command=root.quit, state='disabled')
        self.exit_button.pack(pady=5)

        self.running = False
        self.vs_dev_cmd = None

    def log(self, message):
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(f"[{datetime.datetime.now().strftime('%a %m/%d/%Y %H:%M:%S.%f')}] {message}\n")

    def update_status(self, message):
        self.status_text.config(state='normal')
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.config(state='disabled')
        self.status_text.see(tk.END)
        self.root.update()

    def find_visual_studio(self):
        # First, try checking PATH for cl.exe
        if shutil.which("cl"):
            self.log("Visual Studio found via PATH")
            return True

        # If not in PATH, search common Visual Studio 2022 installation paths
        vs_paths = [
            os.path.join(BASE_DIR, "vcpkg", "installed", "x64-windows", "tools", "msvc"),
            r"C:\Program Files\Microsoft Visual Studio\2022\Community",
            r"C:\Program Files\Microsoft Visual Studio\2022\Professional",
            r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise"
        ]
        for vs_path in vs_paths:
            if os.path.exists(vs_path):
                msvc_path = os.path.join(vs_path, "VC", "Tools", "MSVC")
                if os.path.exists(msvc_path):
                    msvc_versions = glob.glob(os.path.join(msvc_path, "*"))
                    if msvc_versions:
                        latest_version = max(msvc_versions, key=os.path.getmtime)
                        cl_path = os.path.join(latest_version, "bin", "Hostx64", "x64", "cl.exe")
                        if os.path.exists(cl_path):
                            self.log(f"Visual Studio found at {vs_path}")
                            os.environ["PATH"] += os.pathsep + os.path.dirname(cl_path)
                            vs_dev_cmd_path = os.path.join(vs_path, "Common7", "Tools", "VsDevCmd.bat")
                            if os.path.exists(vs_dev_cmd_path):
                                self.vs_dev_cmd = vs_dev_cmd_path
                                self.log(f"VsDevCmd.bat found at {vs_dev_cmd_path}")
                            return True
        self.log("Visual Studio not found in common paths")
        return False

    def run_in_vs_env(self, command):
        if self.vs_dev_cmd:
            cmd = f'cmd /c ""{self.vs_dev_cmd}" && cd /d "{os.getcwd()}" && {" ".join(command)}"'
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True, check=False)
            return result
        else:
            return subprocess.run(command, capture_output=True, text=True, check=False)

    def find_cmakelists(self, start_dir):
        """Search for CMakeLists.txt starting from start_dir and return its directory."""
        for root, dirs, files in os.walk(start_dir):
            if "CMakeLists.txt" in files:
                return root
        return None

    def manual_asset_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Asset Setup")
        dialog.geometry("500x300")
        dialog.grab_set()  # Modal

        msg = Label(dialog, text="Automatic download is not available. Please manually download and place the assets:\n\n1. Download 21900.zip from the link below.\n2. Extract 21900.zip, then extract assets.zip inside it.\n3. Copy 'content' and 'mst' folders to:\n" + GAME_CONTENT_DIR + "\n\nClick the link to open in browser:", wraplength=480, justify="left")
        msg.pack(pady=10)

        link = Label(dialog, text=ASSET_URL, fg="blue", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(ASSET_URL))

        tk.Label(dialog, text="Once placed, click OK to continue.", wraplength=480).pack(pady=10)

        ok_button = tk.Button(dialog, text="OK", command=dialog.destroy)
        ok_button.pack(pady=10)

        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent close until OK
        self.root.wait_window(dialog)

    def cmake_install_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Install CMake")
        dialog.geometry("500x200")
        dialog.grab_set()  # Modal

        msg = Label(dialog, text="CMake is not installed.\n\n1. Click the link below to open the download page.\n2. Download the latest Windows installer (e.g., cmake-3.29.3-windows-x86_64.msi).\n3. Run the installer and select 'Add CMake to the system PATH for all users'.\n4. Once installed, click 'Close Tutorial', manually close this program, and relaunch it to refresh the CMake path.", wraplength=480, justify="left")
        msg.pack(pady=10)

        link = Label(dialog, text=CMAKE_URL, fg="blue", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(CMAKE_URL))

        close_button = tk.Button(dialog, text="Close Tutorial", command=lambda: dialog.destroy())
        close_button.pack(pady=10)

        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent close until Close Tutorial
        self.root.wait_window(dialog)

    def vs_install_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Install Visual Studio")
        dialog.geometry("500x300")
        dialog.grab_set()  # Modal

        msg = Label(dialog, text="Visual Studio 2022 with C++ tools is not detected.\n\n1. Click the link below to open the download page.\n2. Download Visual Studio 2022 Community (it's free).\n3. Run the installer and select 'Desktop development with C++'.\n4. Ensure 'Windows 10 SDK' and 'MSVC v143 - VS 2022 C++ x64/x86 build tools' are checked.\n5. Install (this may take ~10.7 GB).\n6. Once installed, click OK to continue.", wraplength=480, justify="left")
        msg.pack(pady=10)

        link = Label(dialog, text=VS_URL, fg="blue", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open_new(VS_URL))

        ok_button = tk.Button(dialog, text="OK", command=dialog.destroy)
        ok_button.pack(pady=10)

        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent close until OK
        self.root.wait_window(dialog)

    def start_setup_thread(self):
        if not self.running:
            self.running = True
            self.start_button.config(state='disabled')
            # Prompt for root directory before setup
            global BASE_DIR, VCPKG_ROOT, REPO_BASE_DIR, SERVER_DIR, VCPKG_TOOLCHAIN, VCPKG_CACHE, DEPLOY_DIR, GAME_CONTENT_DIR, VS_PROJECT, LOG_FILE
            default_dir = os.path.join(os.getenv("USERPROFILE"), "BF")
            previous_dir = load_previous_dir()
            if previous_dir and os.path.exists(previous_dir):
                BASE_DIR = previous_dir
            else:
                dir_path = filedialog.asksaveasfilename(title="Select or Create Root Directory", initialdir=os.path.dirname(default_dir), initialfile=os.path.basename(default_dir), filetypes=[("Directory", "*")], defaultextension="")
                if not dir_path or dir_path == default_dir:  # Use default if canceled or unchanged
                    dir_path = default_dir
                BASE_DIR = os.path.abspath(dir_path)
                os.makedirs(BASE_DIR, exist_ok=True)
                save_dir_choice()
                messagebox.showinfo("Directory Confirmation", f"Root directory set to {BASE_DIR}. A new folder will be created if it doesn't exist. Click OK to proceed.")
            VCPKG_ROOT = os.path.join(BASE_DIR, "vcpkg")
            REPO_BASE_DIR = os.path.join(BASE_DIR, "BF-WorkingDir", "server")
            SERVER_DIR = os.path.join(REPO_BASE_DIR, "server")
            VCPKG_TOOLCHAIN = os.path.join(VCPKG_ROOT, "scripts", "buildsystems", "vcpkg.cmake")
            VCPKG_CACHE = os.path.join(VCPKG_ROOT, "downloads")
            DEPLOY_DIR = os.path.join(SERVER_DIR, "deploy")
            GAME_CONTENT_DIR = os.path.join(DEPLOY_DIR, "game_content")
            VS_PROJECT = os.path.join(SERVER_DIR, "standalone_frontend", "gimuserverw.vcxproj")
            LOG_FILE = os.path.join(BASE_DIR, "setup.log")
            init_log()
            self.log(f"Root directory set to {BASE_DIR}. This will be used for all setup files.")
            threading.Thread(target=self.run_setup, daemon=True).start()

    def run_setup(self):
        global SERVER_DIR, DEPLOY_DIR, GAME_CONTENT_DIR, VS_PROJECT
        try:
            self.update_status("Starting Brave Frontier server setup...")

            # Step 1: Check for prerequisites
            self.update_status("Step 1 of 10: Checking for Git...")
            if not shutil.which("git"):
                self.log("Git not found")
                messagebox.showinfo("Install Git", "Git is not installed.\n\n1. Open your browser and go to https://git-scm.com/download/win\n2. Download and run the installer.\n3. Follow the setup wizard (default options are fine).\n4. Once installed, click OK to continue.")
                self.update_status("Waiting for Git installation...")
                while not shutil.which("git"):
                    time.sleep(1)
            self.log("Git found")
            self.update_status("Git is installed.")

            self.update_status("Step 2 of 10: Checking for CMake...")
            if not shutil.which("cmake"):
                self.log("CMake not found")
                self.cmake_install_prompt()
                self.update_status("Waiting for CMake installation and restart...")
                return  # Exit to restart
            self.log("CMake found")
            self.update_status("CMake is installed.")

            self.update_status("Step 3 of 10: Checking for Visual Studio 2022...")
            if not self.find_visual_studio():
                self.log("Visual Studio (cl.exe) not found")
                self.vs_install_prompt()
                self.update_status("Waiting for Visual Studio installation...")
                while not self.find_visual_studio():
                    time.sleep(1)
            self.log("Visual Studio found")
            self.update_status("Visual Studio 2022 is installed.")

            self.update_status("Step 4 of 10: Checking for PowerShell...")
            if not shutil.which("powershell"):
                self.log("PowerShell not found")
                messagebox.showerror("Error", "PowerShell is not installed. This is unusual for Windows.\nPlease ensure PowerShell is available on your system.\nSee setup.log for details.")
                self.exit_button.config(state='normal')
                return
            self.log("PowerShell found")
            self.update_status("PowerShell is installed.")

            self.update_status("All required tools are present!")

            # Step 2: Create base directory
            self.update_status("Step 5 of 10: Setting up directories...")
            os.makedirs(BASE_DIR, exist_ok=True)
            self.log(f"Directories set up at {BASE_DIR}")
            self.update_status("Directories are set up.")

            # Step 3: Clone or sync the server repository
            self.update_status("Step 6 of 10: Downloading the server code...")
            if os.path.exists(REPO_BASE_DIR):
                self.update_status("Syncing server repository...")
                os.chdir(REPO_BASE_DIR)
                result = subprocess.run(["git", "pull"], capture_output=True, text=True)
                self.log(f"git pull stdout: {result.stdout}")
                self.log(f"git pull stderr: {result.stderr}")
                result.check_returncode()
                self.log("Server repository synced")
            else:
                self.update_status("Cloning server repository...")
                result = subprocess.run(["git", "clone", "--depth=1", REPO_URL, REPO_BASE_DIR], capture_output=True, text=True)
                self.log(f"git clone command: {' '.join(['git', 'clone', '--depth=1', REPO_URL, REPO_BASE_DIR])}")
                self.log(f"git clone stdout: {result.stdout}")
                self.log(f"git clone stderr: {result.stderr}")
                result.check_returncode()
                self.log("Server repository cloned")

            # Ensure deploy/ is ignored in .gitignore
            gitignore_path = os.path.join(REPO_BASE_DIR, '.gitignore')
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if 'deploy/' not in content:
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    f.write('\ndeploy/')
                self.log("Added deploy/ to .gitignore")

            # Log the directory structure to diagnose file locations
            self.log("Listing repository directory structure:")
            for root, dirs, files in os.walk(REPO_BASE_DIR):
                if 'game_content' in root:
                    continue  # Skip logging subdirs of game_content to avoid huge log
                level = root.replace(REPO_BASE_DIR, '').count(os.sep)
                indent = ' ' * 4 * level
                self.log(f"{indent}{os.path.basename(root)}/")
                for f in files:
                    self.log(f"{indent}    {f}")
            self.update_status("Server code downloaded.")

            # Step 4: Check and install vcpkg
            self.update_status("Step 7 of 10: Setting up vcpkg (library manager)...")
            # Unset VCPKG_ROOT environment variable to avoid mismatch warnings
            if "VCPKG_ROOT" in os.environ:
                self.log(f"Removing VCPKG_ROOT environment variable: {os.environ['VCPKG_ROOT']}")
                del os.environ["VCPKG_ROOT"]
            # Set vcpkg binary cache to local directory
            os.environ["VCPKG_DEFAULT_BINARY_CACHE"] = VCPKG_CACHE
            self.log(f"Set VCPKG_DEFAULT_BINARY_CACHE to {VCPKG_CACHE}")
            if not os.path.exists(VCPKG_ROOT):
                self.update_status("Downloading vcpkg...")
                result = subprocess.run(["git", "clone", "https://github.com/microsoft/vcpkg.git", VCPKG_ROOT], capture_output=True, text=True)
                self.log(f"vcpkg clone stdout: {result.stdout}")
                self.log(f"vcpkg clone stderr: {result.stderr}")
                result.check_returncode()
                self.log("vcpkg cloned")
                self.update_status("Bootstrapping vcpkg...")
                result = subprocess.run([os.path.join(VCPKG_ROOT, "bootstrap-vcpkg.bat"), "-disableMetrics"], capture_output=True, text=True)
                self.log(f"vcpkg bootstrap stdout: {result.stdout}")
                self.log(f"vcpkg bootstrap stderr: {result.stderr}")
                result.check_returncode()
                self.log("vcpkg bootstrapped")
            else:
                self.update_status("vcpkg already set up.")
            self.update_status("Integrating vcpkg...")
            result = subprocess.run([os.path.join(VCPKG_ROOT, "vcpkg.exe"), "integrate", "install"], capture_output=True, text=True)
            self.log(f"vcpkg integrate stdout: {result.stdout}")
            self.log(f"vcpkg integrate stderr: {result.stderr}")
            result.check_returncode()
            self.log("vcpkg integrated")
            self.update_status("vcpkg setup complete.")

            # Step 5: Install dependencies
            self.update_status("Step 8 of 10: Installing required libraries...")
            self.update_status("This step may take ~16 minutes. Please wait...")
            os.chdir(REPO_BASE_DIR)
            result = subprocess.run([os.path.join(VCPKG_ROOT, "vcpkg.exe"), "install"], capture_output=True, text=True)
            self.log(f"vcpkg install stdout: {result.stdout}")
            self.log(f"vcpkg install stderr: {result.stderr}")
            result.check_returncode()
            self.log("Dependencies installed")
            self.update_status("Libraries installed.")

            # Step 6: Verify server directory and required files
            # First, check if CMakeLists.txt exists in the expected SERVER_DIR
            if not os.path.exists(os.path.join(SERVER_DIR, "CMakeLists.txt")):
                self.log(f"CMakeLists.txt not found in expected location: {SERVER_DIR}")
                # Search for CMakeLists.txt in the repository
                cmakelists_dir = self.find_cmakelists(REPO_BASE_DIR)
                if cmakelists_dir:
                    self.log(f"Found CMakeLists.txt at {cmakelists_dir}")
                    # Adjust SERVER_DIR to the directory containing CMakeLists.txt
                    SERVER_DIR = cmakelists_dir
                    # Update dependent paths
                    DEPLOY_DIR = os.path.join(SERVER_DIR, "deploy")
                    GAME_CONTENT_DIR = os.path.join(DEPLOY_DIR, "game_content")
                    VS_PROJECT = os.path.join(SERVER_DIR, "standalone_frontend", "gimuserverw.vcxproj")
                else:
                    self.log("Missing CMakeLists.txt in entire repository")
                    messagebox.showerror("Error", f"Server code is incomplete (missing CMakeLists.txt in {REPO_BASE_DIR}).\nSee setup.log for details.")
                    self.exit_button.config(state='normal')
                    return
            if not os.path.exists(os.path.join(SERVER_DIR, "CMakePresets.json")):
                self.log("Missing CMakePresets.json")
                messagebox.showerror("Error", f"Server code is incomplete (missing CMakePresets.json in {SERVER_DIR}).\nSee setup.log for details.")
                self.exit_button.config(state='normal')
                return

            # Step 7: Run CMake configuration
            self.update_status("Step 9 of 10: Configuring the server... (~10 minutes)")
            os.chdir(SERVER_DIR)
            result = self.run_in_vs_env(["cmake", "--preset", CONFIGURE_PRESET])
            self.log(f"cmake configure stdout: {result.stdout}")
            self.log(f"cmake configure stderr: {result.stderr}")
            result.check_returncode()
            # Check if VS_PROJECT exists; re-run if not
            if not os.path.exists(VS_PROJECT):
                self.log("Re-running CMake configuration as gimuserverw.vcxproj missing.")
                result = self.run_in_vs_env(["cmake", "--preset", CONFIGURE_PRESET])
                self.log(f"re-cmake configure stdout: {result.stdout}")
                self.log(f"re-cmake configure stderr: {result.stderr}")
                result.check_returncode()
            self.log("CMake configuration complete")
            self.update_status("Server configured.")

            # Step 8: Build the server
            self.update_status("Building the server...")
            result = self.run_in_vs_env(["cmake", "--build", ".", "--config", "Debug", "--verbose"])
            self.log(f"cmake build stdout: {result.stdout}")
            self.log(f"cmake build stderr: {result.stderr}")
            result.check_returncode()
            self.log("Build complete")
            self.update_status("Server built successfully.")

            # Step 9: Create deploy and game_content directories
            os.makedirs(DEPLOY_DIR, exist_ok=True)
            os.makedirs(GAME_CONTENT_DIR, exist_ok=True)

            # Step 10: Manual asset setup
            self.update_status("Step 10 of 10: Setting up game assets (manual step)...")
            if not os.path.exists(os.path.join(GAME_CONTENT_DIR, "content")):
                self.manual_asset_prompt()
                while not os.path.exists(os.path.join(GAME_CONTENT_DIR, "content")) or not os.path.exists(os.path.join(GAME_CONTENT_DIR, "mst")):
                    time.sleep(1)
            else:
                self.update_status("Assets already set up.")
            self.log("Assets setup complete")
            self.update_status("Game assets set up.")

            # Step 11: Copy and prefill config.json
            if not os.path.exists(os.path.join(DEPLOY_DIR, "config.json")):
                self.update_status("Copying configuration file...")
                shutil.copy(os.path.join(SERVER_DIR, "config-sample.json"), os.path.join(DEPLOY_DIR, "config.json"))
                with open(os.path.join(DEPLOY_DIR, "config.json"), "w", encoding='utf-8') as f:
                    f.write('{\n  "database_host": "localhost",\n  "database_port": 3306,\n  "database_user": "your_username",\n  "database_password": "your_password",\n  "database_name": "bravefrontier_db"\n}')
                self.log("Copied and prefilled config.json")

            # Step 12: Modify Visual Studio project settings
            self.update_status("Configuring Visual Studio project...")
            ET.register_namespace("", "http://schemas.microsoft.com/developer/msbuild/2003")
            tree = ET.parse(VS_PROJECT)
            root = tree.getroot()
            ns = "http://schemas.microsoft.com/developer/msbuild/2003"
            for config in root.findall(".//{http://schemas.microsoft.com/developer/msbuild/2003}PropertyGroup[@Condition]"):
                wd = ET.SubElement(config, "{http://schemas.microsoft.com/developer/msbuild/2003}WorkingDirectory")
                wd.text = DEPLOY_DIR
            tree.write(VS_PROJECT, encoding="utf-8", xml_declaration=False)
            self.log("VS project configured with debugging working directory set to deploy folder")

            # Step 13: Final instructions
            self.update_status("\nSetup completed successfully!\n")
            self.update_status("Now, follow these steps to run the server:\n")
            self.update_status("1. Edit the configuration file:")
            self.update_status(f"   - Open {os.path.join(DEPLOY_DIR, 'config.json')} in Notepad.")
            self.update_status("   - Replace 'your_username' and 'your_password' with your database credentials (or leave blank for offline SQLite).")
            self.update_status(f"   - If needed, edit {os.path.join(DEPLOY_DIR, 'gimuconfig.json')} and JSON files in {os.path.join(DEPLOY_DIR, 'system')}.")
            self.update_status("   - Save and close the files.")
            self.update_status("Click OK to open config.json in Notepad...")
            messagebox.showinfo("Edit Config", "Click OK to open config.json in Notepad.\nEdit the file, save it, and close Notepad to continue.")
            subprocess.run(["notepad", os.path.join(DEPLOY_DIR, "config.json")])

            self.update_status("\n2. Open the server project in Visual Studio:")
            self.update_status(f"   - Double-click {VS_PROJECT} to open it in Visual Studio 2022.")
            self.update_status("   - In Visual Studio, in the Solution Explorer (usually on the right):")
            self.update_status("     - Right-click on 'gimuserverw'.")
            self.update_status("     - Select 'Set as Startup Project'.")
            self.update_status("Click OK to open the project in Visual Studio...")
            self.update_status("   - In Visual Studio, in the Toolbar (usually at the top):")
            self.update_status("     - Left-click on 'Debug'.")
            self.update_status("     - Select 'gimuserverw Debug Properties'.")
            self.update_status("     - Left-click 'Debugging'.")
            self.update_status("     - Left-click the dropdown next to 'Working Directory' and Select 'Browse...'.")
            self.update_status("     - Navigate to and Select the 'deploy' folder on the root of the 'server' directory (The folder containing all of the game assets you extracted earlier).")
            
            messagebox.showinfo("Open Visual Studio", "Click OK to open the project in Visual Studio.\nSet 'gimuserverw' as the Startup Project as instructed.")
            subprocess.run(["start", "", VS_PROJECT], shell=True)

            self.update_status("\n3. Run the server:")
            self.update_status("   - In Visual Studio, click the green Play button (Local Windows Debugger) at the top.")
            self.update_status("   - The server should start running with the working directory set to the deploy folder.")
            self.update_status("\n4. Next steps:")
            self.update_status("   - Follow the game client setup tutorial to connect to your server.")
            self.update_status(f"   - If you encounter errors, check {LOG_FILE} for details.")
            self.update_status(f"   - For all future launches of the server, open the GimuServer.sln file located in the root of the server directory.")

            self.exit_button.config(state='normal')
        except Exception as e:
            self.log(f"Error during setup: {str(e)}")
            messagebox.showerror("Error", f"An error occurred during setup:\n{str(e)}\n\nSee {LOG_FILE} for details.")
            self.exit_button.config(state='normal')
        finally:
            self.running = False

if __name__ == "__main__":
    root = tk.Tk()
    app = SetupApp(root)
    root.mainloop()
