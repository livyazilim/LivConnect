# © 2025 Liv Yazılım ve Danışmanlık Ltd. Şti.

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import subprocess
import shutil
import re
import datetime
import platform
import threading
import json
import time

# Tray Support
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    print("pystray/Pillow module not found. Tray disabled.")

# Platform Constants
SYSTEM_OS = platform.system()
IS_MAC = (SYSTEM_OS == 'Darwin')

if IS_MAC:
    if os.path.exists("/opt/homebrew/etc/ipsec.conf"):
        BASE_ETC = "/opt/homebrew/etc"
    else:
        BASE_ETC = "/usr/local/etc"
else:
    BASE_ETC = "/etc"

IPSEC_CONF = os.path.join(BASE_ETC, "ipsec.conf")
IPSEC_SECRETS = os.path.join(BASE_ETC, "ipsec.secrets")

# UI Colors
COLOR_BG = "#f0f2f5"
COLOR_SIDEBAR = "#ffffff"
COLOR_PRIMARY = "#2196f3"
COLOR_SUCCESS = "#4caf50"
COLOR_DANGER = "#f44336"
COLOR_WARNING = "#ff9800"
COLOR_TEXT = "#333333"
COLOR_NETWORK = "#673ab7" # Network Manager Purple

class LivConnectApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LivConnect - Enterprise VPN & Network Suite")
        self.root.geometry("1250x850")
        self.root.configure(bg=COLOR_BG)

        icon_path = os.path.join(os.path.dirname(__file__), "livconnect.png")
        if os.path.exists(icon_path):
            try:
                img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, img)
            except Exception as e:
                print(f"Icon load error: {e}")

        # Window Protocol
        self.is_minimized = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # State Variables
        self.current_process = None
        self.active_ipsec_conn = None
        self.is_connecting = False
        self.connected_profile_name = None 

        # Directories
        self.user_home = os.path.expanduser("~")
        self.base_dir = os.path.join(self.user_home, "Documents", "LivConnect")
        self.forti_dir = os.path.join(self.base_dir, "forti")
        self.ipsec_dir = os.path.join(self.base_dir, "ipsec")
        self.net_dir = os.path.join(self.base_dir, "network_profiles")
        self.check_local_folders()

        # UI Init
        self.setup_styles()
        self.create_menu_bar()
        self.setup_ui_components()

        self.log_message(f"LivConnect v1.5 initialized on {SYSTEM_OS}.")
        
        # Tray Thread
        if HAS_TRAY:
            threading.Thread(target=self.init_tray_icon, daemon=True).start()

        # Background Monitor
        self.monitor_vpn_status()

    # -------------------------------------------------------------------------
    # UI COMPONENTS (MODULAR)
    # -------------------------------------------------------------------------
    def setup_ui_components(self):
        # Footer (Initialized but managed by view switcher)
        self.action_bar = tk.Frame(self.root, bg="white", height=60, pady=10, padx=10, bd=1, relief="raised")
        
        self.status_canvas = tk.Canvas(self.action_bar, width=20, height=20, bg="white", highlightthickness=0)
        self.status_canvas.pack(side=tk.LEFT, padx=5)
        self.status_circle = self.status_canvas.create_oval(2, 2, 18, 18, fill="#bdbdbd", outline="") 
        
        self.status_label = tk.Label(self.action_bar, text="Status: Ready", bg="white", font=("Segoe UI", 11))
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.btn_disconnect = tk.Button(self.action_bar, text="■ DISCONNECT VPN", bg=COLOR_DANGER, fg="white", font=("Segoe UI", 10, "bold"), bd=0, padx=20, pady=8, command=self.disconnect_vpn, state="disabled", cursor="hand2")
        self.btn_disconnect.pack(side=tk.RIGHT, padx=5)

        self.btn_connect = tk.Button(self.action_bar, text="▶ CONNECT VPN", bg=COLOR_SUCCESS, fg="white", font=("Segoe UI", 10, "bold"), bd=0, padx=20, pady=8, command=self.connect_vpn, cursor="hand2")
        self.btn_connect.pack(side=tk.RIGHT, padx=5)

        # Split Pane
        self.main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=4)
        self.main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ----------------- SIDEBAR -----------------
        self.sidebar_frame = tk.Frame(self.main_pane, bg=COLOR_SIDEBAR, width=280)
        self.main_pane.add(self.sidebar_frame)

        # Header
        header_frame = tk.Frame(self.sidebar_frame, bg=COLOR_SIDEBAR, pady=15)
        header_frame.pack(fill=tk.X, padx=10)
        tk.Label(header_frame, text="LivConnect", font=("Segoe UI", 18, "bold"), bg=COLOR_SIDEBAR, fg="#1a237e").pack(side=tk.LEFT)

        # MODULE SELECTION
        mod_frame = tk.LabelFrame(self.sidebar_frame, text="Module Select", bg=COLOR_SIDEBAR, pady=10, padx=5, font=("Segoe UI", 9, "bold"))
        mod_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self.protocol_var = tk.StringVar(value="forti")
        rb_style = {"indicatoron": 0, "bg": "#e3f2fd", "fg": COLOR_TEXT, "font": ("Segoe UI", 10, "bold"), "pady": 6}
        
        tk.Radiobutton(mod_frame, text="FortiSSL VPN", variable=self.protocol_var, value="forti", selectcolor=COLOR_PRIMARY, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)
        tk.Radiobutton(mod_frame, text="IPsec / IKEv2", variable=self.protocol_var, value="ipsec", selectcolor=COLOR_PRIMARY, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)
        tk.Radiobutton(mod_frame, text="Network Manager", variable=self.protocol_var, value="network", selectcolor=COLOR_NETWORK, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)

        # VPN PROFILE LIST
        self.vpn_list_container = tk.Frame(self.sidebar_frame, bg=COLOR_SIDEBAR)
        self.vpn_list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(self.vpn_list_container, text="VPN Profiles", bg=COLOR_SIDEBAR, fg="gray", font=("Segoe UI", 9)).pack(anchor="w", pady=(10,0))
        list_scroll = tk.Scrollbar(self.vpn_list_container)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox = tk.Listbox(self.vpn_list_container, font=("Segoe UI", 11), bd=0, highlightthickness=0, bg=COLOR_SIDEBAR, selectbackground="#e3f2fd", selectforeground="#0d47a1", activestyle="none", exportselection=False, yscrollcommand=list_scroll.set)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        list_scroll.config(command=self.file_listbox.yview)
        self.file_listbox.bind('<<ListboxSelect>>', self.load_selected_profile)

        # VPN ACTIONS
        self.vpn_btns_frame = tk.Frame(self.sidebar_frame, bg=COLOR_SIDEBAR)
        self.vpn_btns_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(self.vpn_btns_frame, text="🗑️", bg="#ffcdd2", fg="#c62828", bd=0, font=("Segoe UI", 10), width=4, pady=8, command=self.delete_profile, cursor="hand2").pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(self.vpn_btns_frame, text="➕ Create Profile", bg="#eeeeee", fg="#333", bd=0, font=("Segoe UI", 10), pady=8, command=self.create_new_profile, cursor="hand2").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ----------------- RIGHT CONTENT AREA -----------------
        self.content_container = tk.Frame(self.main_pane, bg=COLOR_BG)
        self.main_pane.add(self.content_container)

        # -- VIEW 1: VPN EDITOR --
        self.vpn_view_frame = tk.Frame(self.content_container, bg=COLOR_BG)
        
        editor_header = tk.Frame(self.vpn_view_frame, bg=COLOR_BG, pady=5)
        editor_header.pack(fill=tk.X)
        self.lbl_editor_title = tk.Label(editor_header, text="VPN Configuration", font=("Segoe UI", 12, "bold"), bg=COLOR_BG)
        self.lbl_editor_title.pack(side=tk.LEFT)
        
        header_btns = tk.Frame(editor_header, bg=COLOR_BG)
        header_btns.pack(side=tk.RIGHT)
        
        self.btn_get_cert = tk.Button(header_btns, text="🛡️ Get/Trust Cert", bg=COLOR_WARNING, fg="white", font=("Segoe UI", 9, "bold"), bd=0, padx=10, pady=5, command=self.detect_forti_cert, cursor="hand2")
        self.btn_get_cert.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(header_btns, text="💾 Save Config", bg=COLOR_PRIMARY, fg="white", font=("Segoe UI", 9, "bold"), bd=0, padx=15, pady=5, command=self.save_profile, cursor="hand2").pack(side=tk.LEFT)

        self.notebook = ttk.Notebook(self.vpn_view_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        self.tab1_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.tab1_frame, text="  VPN Config (.conf)  ")
        self.editor_conf = scrolledtext.ScrolledText(self.tab1_frame, font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.editor_conf.pack(fill=tk.BOTH, expand=True)

        self.tab2_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.tab2_frame, text="  VPN Secrets (.secrets)  ")
        self.editor_sec = scrolledtext.ScrolledText(self.tab2_frame, font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.editor_sec.pack(fill=tk.BOTH, expand=True)

        # -- VIEW 2: NETWORK MANAGER --
        self.net_view_frame = tk.Frame(self.content_container, bg=COLOR_BG)
        self.setup_network_manager_ui(self.net_view_frame)

        # Logs (Shared)
        self.log_frame = tk.LabelFrame(self.content_container, text="System Logs", font=("Segoe UI", 9, "bold"), bg=COLOR_BG, fg="gray")
        self.log_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(10, 0), ipady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=6, font=("Consolas", 9), bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.tag_config("INFO", foreground="#00ff00")
        self.log_text.tag_config("ERROR", foreground="#ff5252")
        self.log_text.tag_config("WARN", foreground="orange")
        self.log_text.tag_config("DEBUG", foreground="cyan")
        
        # Initial View Load
        self.switch_main_view()

    # -------------------------------------------------------------------------
    # VIEW SWITCHING LOGIC
    # -------------------------------------------------------------------------
    def switch_main_view(self):
        """Swaps between VPN Editor and Network Manager views."""
        mode = self.protocol_var.get()
        
        self.vpn_view_frame.pack_forget()
        self.net_view_frame.pack_forget()

        if mode == "network":
            # Show Network Manager
            self.net_view_frame.pack(fill=tk.BOTH, expand=True)
            self.vpn_list_container.pack_forget()
            self.vpn_btns_frame.pack_forget()
            # Hide VPN Footer
            self.action_bar.pack_forget()
        else:
            # Show VPN Editor
            self.vpn_view_frame.pack(fill=tk.BOTH, expand=True)
            # Show VPN specific sidebar elements
            self.vpn_list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            self.vpn_btns_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
            # Show VPN Footer
            self.action_bar.pack(side=tk.BOTTOM, fill=tk.X)
            
            self.update_ui_mode()
            self.toggle_buttons(self.current_process is not None or self.active_ipsec_conn is not None)

    # -------------------------------------------------------------------------
    # NETWORK MANAGER UI SETUP
    # -------------------------------------------------------------------------
    def setup_network_manager_ui(self, parent):
        header = tk.Frame(parent, bg=COLOR_BG, pady=5)
        header.pack(fill=tk.X)
        tk.Label(header, text="Network & Routing Manager", font=("Segoe UI", 16, "bold"), fg=COLOR_NETWORK, bg=COLOR_BG).pack(side=tk.LEFT, padx=10)

        # 1. Profile Manager Bar
        top_frame = tk.LabelFrame(parent, text="Profiles", bg="white", pady=10, padx=10)
        top_frame.pack(fill=tk.X, padx=10)

        tk.Label(top_frame, text="Select Profile:", bg="white").pack(side=tk.LEFT, padx=5)
        self.net_profile_combo = ttk.Combobox(top_frame, width=25, state="readonly")
        self.net_profile_combo.pack(side=tk.LEFT, padx=5)
        self.net_profile_combo.bind("<<ComboboxSelected>>", self.load_network_profile)

        tk.Button(top_frame, text="💾 Save", bg="#e0e0e0", command=self.save_network_profile).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="➕ New", bg="#e0e0e0", command=self.create_network_profile).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="🗑️ Delete", bg="#ffcdd2", command=self.delete_network_profile).pack(side=tk.LEFT, padx=5)

        # 2. Interface IP Configuration (Static vs DHCP)
        self.ip_mode_var = tk.StringVar(value="auto")
        
        iface_frame = tk.LabelFrame(parent, text="Interface Configuration (Wi-Fi / Ethernet)", bg="white", padx=10, pady=10, font=("Segoe UI", 10, "bold"))
        iface_frame.pack(fill=tk.X, padx=10, pady=10)

        # Radio Buttons
        tk.Radiobutton(iface_frame, text="Automatic (DHCP)", variable=self.ip_mode_var, value="auto", bg="white", font=("Segoe UI", 9), command=self.toggle_ip_inputs).pack(anchor="w")
        tk.Radiobutton(iface_frame, text="Manual (Static IP)", variable=self.ip_mode_var, value="manual", bg="white", font=("Segoe UI", 9), command=self.toggle_ip_inputs).pack(anchor="w")

        # Inputs
        grid_frame = tk.Frame(iface_frame, bg="white")
        grid_frame.pack(fill=tk.X, pady=5, padx=20)
        
        tk.Label(grid_frame, text="IP Address:", bg="white").grid(row=0, column=0, padx=5, sticky="e")
        self.ent_iface_ip = tk.Entry(grid_frame, width=20)
        self.ent_iface_ip.grid(row=0, column=1, padx=5)
        self.ent_iface_ip.insert(0, "192.168.1.150/24")

        tk.Label(grid_frame, text="Gateway:", bg="white").grid(row=0, column=2, padx=5, sticky="e")
        self.ent_iface_gw = tk.Entry(grid_frame, width=20)
        self.ent_iface_gw.grid(row=0, column=3, padx=5)
        self.ent_iface_gw.insert(0, "192.168.1.1")

        tk.Label(grid_frame, text="Primary DNS:", bg="white").grid(row=0, column=4, padx=5, sticky="e")
        self.ent_iface_dns = tk.Entry(grid_frame, width=20)
        self.ent_iface_dns.grid(row=0, column=5, padx=5)
        self.ent_iface_dns.insert(0, "8.8.8.8")

        self.toggle_ip_inputs() # Set initial state

        # 3. Additional Rules (Routes)
        rule_frame = tk.LabelFrame(parent, text="Additional Rules (Static Routes)", bg="white", padx=10, pady=10)
        rule_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Inputs for Routes
        r_frame = tk.Frame(rule_frame, bg="white")
        r_frame.pack(fill=tk.X, pady=2)
        tk.Label(r_frame, text="ROUTE ->", bg="white", width=8, anchor="w", font=("Consolas", 10, "bold"), fg="blue").pack(side=tk.LEFT)
        tk.Label(r_frame, text="Target Subnet:", bg="white").pack(side=tk.LEFT)
        self.ent_target = tk.Entry(r_frame, width=18)
        self.ent_target.pack(side=tk.LEFT, padx=5)
        tk.Label(r_frame, text="Via Gateway:", bg="white").pack(side=tk.LEFT)
        self.ent_gateway = tk.Entry(r_frame, width=15)
        self.ent_gateway.pack(side=tk.LEFT, padx=5)
        
        # Add Route Button
        tk.Button(r_frame, text="Add Route", bg="#bbdefb", command=self.add_route_to_list).pack(side=tk.LEFT, padx=(10, 5))
        
        # Remove Selected Button (Moved here per request)
        tk.Button(r_frame, text="Remove Selected", command=self.remove_net_row, bg="#ffcdd2").pack(side=tk.LEFT, padx=5)

        # Treeview
        columns = ("type", "detail", "gateway")
        self.net_tree = ttk.Treeview(rule_frame, columns=columns, show="headings", height=5)
        self.net_tree.heading("type", text="Type")
        self.net_tree.heading("detail", text="Target Subnet")
        self.net_tree.heading("gateway", text="Gateway")
        self.net_tree.column("type", width=80, anchor="center")
        self.net_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(rule_frame, orient=tk.VERTICAL, command=self.net_tree.yview)
        self.net_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 4. Big Action Button
        apply_frame = tk.Frame(parent, bg="white", pady=15)
        apply_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Big Styled Button
        tk.Button(apply_frame, text="⚡ APPLY CONFIGURATION TO SYSTEM ⚡", bg=COLOR_NETWORK, fg="white", 
                  font=("Segoe UI", 14, "bold"), pady=15, bd=0, cursor="hand2", 
                  activebackground="#512da8", activeforeground="white",
                  command=self.apply_current_net_config).pack(fill=tk.X, padx=20)

        # Init
        self.refresh_net_profiles()

    def toggle_ip_inputs(self):
        state = "normal" if self.ip_mode_var.get() == "manual" else "disabled"
        self.ent_iface_ip.config(state=state)
        self.ent_iface_gw.config(state=state)
        self.ent_iface_dns.config(state=state)

    # --- Network Logic (JSON & Execution) ---
    def refresh_net_profiles(self):
        if not os.path.exists(self.net_dir): os.makedirs(self.net_dir)
        files = [f.replace(".json", "") for f in os.listdir(self.net_dir) if f.endswith(".json")]
        self.net_profile_combo['values'] = sorted(files)

    def create_network_profile(self):
        name = simple_input(self.root, "New Network Profile", "Profile Name:")
        if name:
            path = os.path.join(self.net_dir, name + ".json")
            # Default structure
            default_data = {
                "mode": "auto",
                "ip": "", "gateway": "", "dns": "",
                "routes": []
            }
            with open(path, 'w') as f: json.dump(default_data, f)
            self.refresh_net_profiles()
            self.net_profile_combo.set(name)
            self.load_network_profile(None)

    def delete_network_profile(self):
        name = self.net_profile_combo.get()
        if not name: return
        if messagebox.askyesno("Confirm", "Delete network profile?"):
            os.remove(os.path.join(self.net_dir, name + ".json"))
            self.refresh_net_profiles()
            self.net_profile_combo.set("")
            self.clear_net_tree()

    def save_network_profile(self):
        name = self.net_profile_combo.get()
        if not name: 
            messagebox.showwarning("Save", "Select/Create a profile first.")
            return
        
        routes = []
        for child in self.net_tree.get_children():
            routes.append(self.net_tree.item(child)["values"])
        
        data = {
            "mode": self.ip_mode_var.get(),
            "ip": self.ent_iface_ip.get(),
            "gateway": self.ent_iface_gw.get(),
            "dns": self.ent_iface_dns.get(),
            "routes": routes
        }
        
        with open(os.path.join(self.net_dir, name + ".json"), 'w') as f:
            json.dump(data, f)
        self.log_message(f"Network profile saved: {name}", "INFO")

    def load_network_profile(self, event):
        name = self.net_profile_combo.get()
        path = os.path.join(self.net_dir, name + ".json")
        self.clear_net_tree()
        
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                # Load Mode
                self.ip_mode_var.set(data.get("mode", "auto"))
                self.toggle_ip_inputs()
                
                # Load Inputs
                self.ent_iface_ip.delete(0, tk.END)
                self.ent_iface_ip.insert(0, data.get("ip", ""))
                
                self.ent_iface_gw.delete(0, tk.END)
                self.ent_iface_gw.insert(0, data.get("gateway", ""))
                
                self.ent_iface_dns.delete(0, tk.END)
                self.ent_iface_dns.insert(0, data.get("dns", ""))
                
                # Load Routes
                for route in data.get("routes", []):
                    self.net_tree.insert("", tk.END, values=route)

    def add_route_to_list(self):
        target = self.ent_target.get()
        gw = self.ent_gateway.get()
        if target and gw: self.net_tree.insert("", tk.END, values=("ROUTE", target, gw))
    
    def add_dns_to_list(self):
        # Deprecated in this UI version (handled in Interface Config)
        pass

    def remove_net_row(self):
        sel = self.net_tree.selection()
        for item in sel: self.net_tree.delete(item)

    def clear_net_tree(self):
        for item in self.net_tree.get_children(): self.net_tree.delete(item)

    def get_active_connection_name(self):
        """Returns the active NetworkManager connection name."""
        try:
            # nmcli -t -f NAME,DEVICE connection show --active
            # Returns: Wired connection 1:eth0
            res = subprocess.check_output(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"], text=True)
            if res:
                return res.split('\n')[0].strip() # Return first active connection
        except: return None
        return None

    def apply_current_net_config(self):
        conn_name = self.get_active_connection_name()
        if not conn_name:
            messagebox.showerror("Error", "No active NetworkManager connection found.")
            return

        if not messagebox.askyesno("Apply", f"Apply configuration to interface: '{conn_name}'?\n(Requires Admin Privileges)"): return

        self.log_message(f"Applying config to: {conn_name}", "WARN")
        commands = []

        # 1. Interface Configuration
        if self.ip_mode_var.get() == "manual":
            ip = self.ent_iface_ip.get()
            gw = self.ent_iface_gw.get()
            dns = self.ent_iface_dns.get()
            
            # Set Manual
            commands.append(f"nmcli con mod '{conn_name}' ipv4.method manual")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.addresses {ip}")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.gateway {gw}")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.dns {dns}")
        else:
            # Set Auto (DHCP) - Clear static settings
            commands.append(f"nmcli con mod '{conn_name}' ipv4.method auto")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.addresses ''")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.gateway ''")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.dns ''")

        # 2. Additional Routes (Iterate Treeview)
        # Note: Persistent static routes in NM are ipv4.routes "ip/mask gw"
        # We need to collect them all
        routes_str = ""
        for child in self.net_tree.get_children():
            vals = self.net_tree.item(child)["values"]
            if vals[0] == "ROUTE":
                # nmcli format: "192.168.5.0/24 10.0.0.1"
                routes_str += f"{vals[1]} {vals[2]},"
        
        if routes_str:
            routes_str = routes_str.rstrip(',')
            commands.append(f"nmcli con mod '{conn_name}' ipv4.routes '{routes_str}'")
        else:
            # Clear routes if empty list
            commands.append(f"nmcli con mod '{conn_name}' ipv4.routes ''")

        # 3. Apply Changes (Up the connection)
        commands.append(f"nmcli con up '{conn_name}'")

        # Execute as Root
        full_script = "\n".join(commands)
        self.log_message(f"Executing nmcli commands...", "INFO")
        
        res = self.run_as_root(["sh", "-c", full_script])
        
        if res and res.returncode == 0:
            messagebox.showinfo("Success", "Network configuration applied successfully.")
            self.log_message("Network config applied.", "INFO")
        else:
            err = res.stderr if res else "Unknown Error"
            messagebox.showerror("Failure", f"Failed to apply settings:\n{err}")
            self.log_message(f"Net Apply Fail: {err}", "ERROR")

    # -------------------------------------------------------------------------
    # TRAY IMPLEMENTATION
    # -------------------------------------------------------------------------
    def create_tray_image(self):
        width = 64
        height = 64
        color = (33, 150, 243) 
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((0, 0, width, height), fill=(255, 255, 255))
        dc.ellipse((8, 8, width-8, height-8), fill=color)
        dc.line((24, 16, 24, 48), fill="white", width=5)
        dc.line((22, 46, 44, 46), fill="white", width=5)
        return image

    def _tray_action_closure(self, profile_name, protocol):
        def callback(icon, item):
            self.connect_vpn_from_tray(profile_name, protocol)
        return callback

    def _tray_check_closure(self, profile_name):
        def callback(item):
            return self.connected_profile_name == profile_name
        return callback

    def build_tray_menu(self):
        menu_items = []
        menu_items.append(pystray.MenuItem("Show LivConnect", self.show_window_from_tray, default=True))
        menu_items.append(pystray.Menu.SEPARATOR)

        lbl = "Disconnect"
        if self.connected_profile_name:
            lbl = f"Disconnect ({self.connected_profile_name})"
        
        menu_items.append(pystray.MenuItem(lbl, self.disconnect_vpn_from_tray, enabled=(self.connected_profile_name is not None)))
        menu_items.append(pystray.Menu.SEPARATOR)

        forti_subs = []
        if os.path.exists(self.forti_dir):
            for f in sorted(os.listdir(self.forti_dir)):
                if f.endswith(".vpn"):
                    name = f[:-4]
                    item = pystray.MenuItem(name, self._tray_action_closure(name, "forti"), checked=self._tray_check_closure(name))
                    forti_subs.append(item)
        if forti_subs:
            menu_items.append(pystray.MenuItem("FortiSSL", pystray.Menu(*forti_subs)))

        ipsec_subs = []
        if os.path.exists(self.ipsec_dir):
            for f in sorted(os.listdir(self.ipsec_dir)):
                if f.endswith(".conf"):
                    name = f[:-5]
                    item = pystray.MenuItem(name, self._tray_action_closure(name, "ipsec"), checked=self._tray_check_closure(name))
                    ipsec_subs.append(item)
        if ipsec_subs:
            menu_items.append(pystray.MenuItem("IPsec", pystray.Menu(*ipsec_subs)))

        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Quit", self.quit_app))
        return pystray.Menu(*menu_items)

    def init_tray_icon(self):
        image = self.create_tray_image()
        try:
            menu = self.build_tray_menu()
        except Exception:
            menu = pystray.Menu(pystray.MenuItem("Quit", self.quit_app))
        self.tray_icon = pystray.Icon("LivConnect", image, "LivConnect VPN", menu=menu)
        self.tray_icon.run()

    def update_tray_menu(self):
        if hasattr(self, 'tray_icon') and self.tray_icon.visible:
            try:
                self.tray_icon.menu = self.build_tray_menu()
            except: pass

    def connect_vpn_from_tray(self, profile_name, protocol):
        self.root.after(0, lambda: self.connect_vpn(profile_name, protocol))

    def disconnect_vpn_from_tray(self, icon, item):
        self.root.after(0, self.disconnect_vpn)

    def show_window_from_tray(self, icon, item):
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        try: self.root.focus_force()
        except: pass
        self.is_minimized = False

    def on_closing(self):
        if HAS_TRAY:
            self.root.withdraw()
            if not self.is_minimized:
                try: self.tray_icon.notify("LivConnect is minimized to tray.", "LivConnect")
                except: pass
                self.is_minimized = True
        else:
            if messagebox.askokcancel("Quit", "Exit LivConnect?"):
                self.quit_app()

    def quit_app(self, icon=None, item=None):
        self.disconnect_vpn()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()
        os._exit(0)

    # -------------------------------------------------------------------------
    # VPN OPERATIONS
    # -------------------------------------------------------------------------
    def connect_vpn(self, profile_name=None, protocol=None):
        if profile_name is None:
            selection = self.file_listbox.curselection()
            if not selection: 
                messagebox.showwarning("Warning", "Select a profile.")
                return
            profile_name = self.file_listbox.get(selection[0])
            protocol = self.protocol_var.get()

        current_dir = self.forti_dir if protocol == "forti" else self.ipsec_dir
        self.is_connecting = True
        self.set_status(f"Connecting to {profile_name}...", "working")
        self.root.update()

        if protocol == "forti":
            if self.current_process: 
                self.is_connecting = False
                return 
            path = os.path.join(current_dir, profile_name + ".vpn")
            try:
                if IS_MAC:
                    safe_cmd = f'openfortivpn -c "{path}"'
                    self.current_process = subprocess.Popen(["osascript", "-e", f'do shell script "{safe_cmd}" with administrator privileges'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    self.current_process = subprocess.Popen(["pkexec", "openfortivpn", "-c", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                self.active_ipsec_conn = None 
                self.connected_profile_name = profile_name 
                self.set_status(f"Connected: {profile_name}", "connected")
                self.toggle_buttons(True)
            except Exception as e:
                self.set_status("Error", "error")
                self.log_message(str(e), "ERROR")

        elif protocol == "ipsec":
            conf_path = os.path.join(current_dir, profile_name + ".conf")
            conn_name = self.find_ipsec_conn_name(conf_path)
            
            if not conn_name: 
                self.is_connecting = False
                self.log_message("Connection name not found.", "ERROR")
                return
            
            if self.run_as_root(["ipsec", "update"]).returncode != 0:
                self.set_status("Update Failed", "error")
                self.is_connecting = False
                return
            
            res = self.run_as_root(["ipsec", "up", conn_name])
            if res.returncode == 0:
                self.current_process = None 
                self.active_ipsec_conn = conn_name
                self.connected_profile_name = profile_name 
                self.set_status(f"Connected: {profile_name}", "connected")
                self.log_message("Connection Established", "INFO")
                self.toggle_buttons(True)
            else:
                self.set_status("Error", "error")
                self.log_message(res.stderr + res.stdout, "ERROR")
        
        self.is_connecting = False
        self.update_tray_menu()

    def disconnect_vpn(self):
        if self.current_process:
            if IS_MAC: subprocess.run(["usr/bin/pkill", "openfortivpn"])
            else: subprocess.run(["pkexec", "kill", str(self.current_process.pid)])
            self.current_process = None
            
        elif self.active_ipsec_conn:
            self.run_as_root(["ipsec", "down", self.active_ipsec_conn])
            self.active_ipsec_conn = None
        
        try:
            self.connected_profile_name = None
            self.set_status("Ready", "ready")
            self.toggle_buttons(False)
            self.update_tray_menu()
        except: pass

    def monitor_vpn_status(self):
        if self.is_connecting:
            self.root.after(3000, self.monitor_vpn_status)
            return

        is_forti_up = self.check_process_running("openfortivpn")
        is_ipsec_up = self.check_ipsec_established()

        if is_forti_up:
            self.set_status("FortiVPN Active", "connected")
            self.toggle_buttons(True)
        elif is_ipsec_up:
            self.set_status("IPsec Active", "connected")
            self.toggle_buttons(True)
        else:
            current_txt = self.status_label.cget("text")
            if "Active" in current_txt or "Checking" in current_txt:
                self.set_status("Ready", "ready")
                self.toggle_buttons(False)
                if self.connected_profile_name:
                    self.connected_profile_name = None
                    self.update_tray_menu()
        
        self.root.after(3000, self.monitor_vpn_status)

    # -------------------------------------------------------------------------
    # CONFIG MANAGEMENT
    # -------------------------------------------------------------------------
    def create_new_profile(self):
        top = tk.Toplevel(self.root)
        top.title("New Profile")
        top.geometry("350x160")
        tk.Label(top, text="Profile Name (Alphanumeric):").pack(pady=10)
        e = tk.Entry(top, width=30)
        e.pack(pady=5)
        e.focus_set()
        
        def confirm(event=None):
            name = re.sub(r'[^a-zA-Z0-9_-]', '', e.get().strip())
            if not name: return
            current_dir = self.get_current_dir()
            protocol = self.protocol_var.get()
            
            if protocol == "forti":
                forti_template = f"""# LivConnect FortiSSL Configuration
# Profile: {name}

# --- SERVER SETTINGS ---
host = VPN_SERVER_IP
port = 443

# --- AUTHENTICATION ---
username = YOUR_USERNAME
password = YOUR_PASSWORD

# --- SECURITY & CERTIFICATES ---
# trusted-cert = sha256:...... # Use this if you get a certificate error (check logs)
# ca-file = /path/to/ca.pem    # Use CA file instead of hash
# user-cert = /path/to/cert    # Client certificate
# user-key = /path/to/key      # Client key

# --- NETWORK & ROUTING ---
set-routes = 1                 # 1 = Add routes automatically (Recommended)
set-dns = 1                    # 1 = Update DNS settings (Recommended)
pppd-use-peerdns = 1           # 1 = Use VPN DNS for lookups

# --- ADVANCED ---
# half-internet-routes = 0     # 0 or 1
# realm = realm-name           # If server requires a realm
"""
                with open(os.path.join(current_dir, name + ".vpn"), 'w') as f: f.write(forti_template)
            
            elif protocol == "ipsec":
                conf = f"""# IPsec Configuration for {name}
# Documentation: https://wiki.strongswan.org/projects/strongswan/wiki/ConnSection

conn {name}
    # --- AUTHENTICATION ---
    keyexchange=ikev2              # ikev2 is recommended. Use 'ikev1' for legacy L2TP.
    # authby=secret                # Use PSK (Enable if using Pre-Shared Key)
    # leftauth=psk                 # Local auth via PSK
    # rightauth=psk                # Remote auth via PSK
    
    # EAP (Username/Password) - Most common for Road Warriors
    leftauth=eap-mschapv2
    eap_identity="YOUR_USERNAME"   # Your VPN Username
    rightauth=pubkey               # Server authenticates with certificate

    # --- NETWORK SETTINGS ---
    right=VPN_SERVER_IP            # Remote VPN Server IP or Hostname
    rightid=@server_identity       # Server Identity (often same as hostname)
    rightsubnet=0.0.0.0/0          # Route ALL traffic through VPN
    # rightsubnet=10.0.0.0/8       # Route only specific subnet
    
    left=%defaultroute             # Local Interface
    leftsourceip=%config           # Request Virtual IP (VIP)

    # --- CONNECTION BEHAVIOR ---
    auto=add                       # 'add': Load config but wait for user. 'start': Auto connect.
    dpdaction=clear                # Clear connection if peer is dead
    dpddelay=300s                  # Check every 300s
    fragmentation=yes              # Allow IKE fragmentation

    # --- CRYPTOGRAPHY (Optional - Enable if server requires specific suites) ---
    # ike=aes256-sha256-modp2048!
    # esp=aes256-sha256!
"""
                sec = f"""# Secrets for {name}
# Format: identity : TYPE "value"

# 1. EAP (Username/Password)
YOUR_USERNAME : EAP "YOUR_PASSWORD"

# 2. PSK (Pre-Shared Key) - Uncomment if needed
# YOUR_LOCAL_IP_OR_EMAIL : PSK "YOUR_PRE_SHARED_KEY"
"""
                with open(os.path.join(current_dir, name + ".conf"), 'w') as f: f.write(conf)
                with open(os.path.join(current_dir, name + ".secrets"), 'w') as f: f.write(sec)

            top.destroy()
            self.refresh_profile_list()
            self.update_tray_menu() 
            self.log_message(f"Created: {name}")

        top.bind('<Return>', confirm)
        tk.Button(top, text="CREATE", command=confirm).pack(pady=10)

    def delete_profile(self):
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select profile to delete.")
            return

        profile_name = self.file_listbox.get(selection[0])
        protocol = self.protocol_var.get()
        current_dir = self.get_current_dir()

        if not messagebox.askyesno("Confirm", f"Delete '{profile_name}'?"): return

        try:
            if protocol == "forti":
                p = os.path.join(current_dir, profile_name + ".vpn")
                if os.path.exists(p): os.remove(p)
            elif protocol == "ipsec":
                p1 = os.path.join(current_dir, profile_name + ".conf")
                p2 = os.path.join(current_dir, profile_name + ".secrets")
                if os.path.exists(p1): os.remove(p1)
                if os.path.exists(p2): os.remove(p2)

            self.log_message(f"Deleted: {profile_name}", "WARN")
            self.editor_conf.delete('1.0', tk.END)
            self.editor_sec.delete('1.0', tk.END)
            self.refresh_profile_list()
            self.update_tray_menu()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_profile(self):
        selection = self.file_listbox.curselection()
        if not selection: return
        profile_name = self.file_listbox.get(selection[0])
        current_dir = self.get_current_dir()
        protocol = self.protocol_var.get()
        try:
            ext = ".vpn" if protocol == "forti" else ".conf"
            p1 = os.path.join(current_dir, profile_name + ext)
            with open(p1, 'w') as f: f.write(self.editor_conf.get('1.0', tk.END))
            os.chmod(p1, 0o600)
            if protocol == "ipsec":
                p2 = os.path.join(current_dir, profile_name + ".secrets")
                with open(p2, 'w') as f: f.write(self.editor_sec.get('1.0', tk.END))
                os.chmod(p2, 0o600)
            self.log_message(f"Saved: {profile_name}")
            self.update_tray_menu()
        except Exception as e: messagebox.showerror("Error", str(e))

    # -------------------------------------------------------------------------
    # UTILS & SETTINGS
    # -------------------------------------------------------------------------
    def detect_forti_cert(self):
        selection = self.file_listbox.curselection()
        if not selection: return
        profile_name = self.file_listbox.get(selection[0])
        path = os.path.join(self.get_current_dir(), profile_name + ".vpn")
        
        self.log_message(f"Checking cert: {profile_name}", "WARN")
        self.root.update()
        try:
            full_cmd = ["pkexec", "openfortivpn", "-c", path]
            if IS_MAC:
                safe = f'openfortivpn -c "{path}" 2>&1'
                proc = subprocess.run(["osascript", "-e", f'do shell script "{safe}" with administrator privileges'], capture_output=True, text=True)
                out = proc.stdout + proc.stderr
            else:
                proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
                out = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            self.log_message("Timeout", "ERROR")
            return
        except Exception as e:
            out = str(e)

        match = re.search(r'(?:trusted-cert|digest)\s+([\w]+)', out)
        if match:
            h = match.group(1)
            if messagebox.askyesno("Certificate", f"Hash: {h}\nTrust?"):
                self.append_cert_to_config(h)
        else:
            messagebox.showinfo("Result", "No error detected.")

    def append_cert_to_config(self, h):
        txt = self.editor_conf.get('1.0', tk.END)
        if "trusted-cert" in txt:
            new = re.sub(r'trusted-cert\s*=\s*.*', f'trusted-cert = {h}', txt)
        else:
            new = txt.strip() + f"\ntrusted-cert = {h}\n"
        self.editor_conf.delete('1.0', tk.END)
        self.editor_conf.insert(tk.END, new)
        self.save_profile()

    def open_settings_window(self):
        top = tk.Toplevel(self.root)
        top.title("Settings")
        top.geometry("500x550")
        top.configure(bg=COLOR_BG)
        
        tk.Label(top, text="Configuration", font=("Segoe UI", 14), bg=COLOR_BG).pack(pady=20)
        
        g1 = tk.LabelFrame(top, text="Checks", bg=COLOR_BG, padx=10, pady=10)
        g1.pack(fill=tk.X, padx=15)
        self.check_dependency_ui(g1, "OpenFortiVPN", "openfortivpn")
        self.check_dependency_ui(g1, "StrongSwan", "ipsec")
        if not IS_MAC: self.check_dependency_ui(g1, "Pkexec", "pkexec")

        g2 = tk.LabelFrame(top, text="Install", bg=COLOR_BG, padx=10, pady=10)
        g2.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(g2, text="Add Config (Root)", bg=COLOR_SUCCESS, fg="white", command=lambda: self.manage_includes("install")).pack(fill=tk.X)
        
        g3 = tk.LabelFrame(top, text="Uninstall", bg=COLOR_BG, padx=10, pady=10)
        g3.pack(fill=tk.X, padx=15)
        tk.Button(g3, text="Remove Config (Root)", bg=COLOR_DANGER, fg="white", command=lambda: self.manage_includes("remove")).pack(fill=tk.X)

    def check_dependency_ui(self, p, l, c):
        f = tk.Frame(p, bg=COLOR_BG)
        f.pack(fill=tk.X, pady=2)
        tk.Label(f, text=f"{l}:", bg=COLOR_BG, width=20, anchor="w").pack(side=tk.LEFT)
        exist = shutil.which(c) is not None
        tk.Label(f, text="INSTALLED" if exist else "MISSING", fg=COLOR_SUCCESS if exist else COLOR_DANGER, bg=COLOR_BG).pack(side=tk.LEFT)

    def manage_includes(self, action):
        ci = f"include {self.ipsec_dir}/*.conf"
        si = f"include {self.ipsec_dir}/*.secrets"
        s = ""
        if action == "install":
            s = f"grep -qxF '{ci}' {IPSEC_CONF} || echo '{ci}' >> {IPSEC_CONF}\ngrep -qxF '{si}' {IPSEC_SECRETS} || echo '{si}' >> {IPSEC_SECRETS}\nipsec update"
        elif action == "remove":
            # Raw string to prevent invalid escape sequence warning
            s = rf"sed -i.bak '\|{self.ipsec_dir}|d' {IPSEC_CONF}" + "\n" + rf"sed -i.bak '\|{self.ipsec_dir}|d' {IPSEC_SECRETS}" + "\nipsec update"
        
        self.run_as_root(["sh", "-c", s])
        messagebox.showinfo("Info", "Done.")

    def run_as_root(self, cmd):
        c = " ".join(cmd)
        try:
            if IS_MAC:
                return subprocess.run(["osascript", "-e", f'do shell script "{c}" with administrator privileges'], capture_output=True, text=True)
            else:
                return subprocess.run(["pkexec"] + cmd, capture_output=True, text=True)
        except: return None

    # --- STANDARD HELPERS ---
    def create_menu_bar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        f = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=f)
        f.add_command(label="Settings", command=self.open_settings_window)
        f.add_separator()
        f.add_command(label="Exit", command=self.quit_app)
        h = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=h)
        h.add_command(label="About", command=self.show_about_dialog)

    def show_about_dialog(self):
        about_text = (
            "LivConnect\n"
            "Enterprise VPN Manager\n"
            "Version 1.5\n\n"
            "Developed by: Liv Yazılım\n\n"
            "This software is proudly developed and distributed by Liv Yazılım "
            "in accordance with the principles of the GNU General Public License (GPL).\n\n"
            "Preamble:\n"
            "The licenses for most software are designed to take away your freedom to share "
            "and change it. By contrast, the GNU General Public License is intended to guarantee "
            "your freedom to share and change free software--to make sure the software is free "
            "for all its users.\n\n"
            "We believe in the freedom to run, study, share, and modify software. "
            "This application respects your freedom and privacy.\n\n"
            "© 2025 Liv Yazılım ve Danışmanlık Ltd. Şti."
        )
        
        top = tk.Toplevel(self.root)
        top.title("About LivConnect")
        top.geometry("500x450")
        top.configure(bg="white")
        top.resizable(False, False)

        header = tk.Frame(top, bg=COLOR_PRIMARY, pady=15)
        header.pack(fill=tk.X)
        tk.Label(header, text="LivConnect", font=("Segoe UI", 16, "bold"), fg="white", bg=COLOR_PRIMARY).pack()
        tk.Label(header, text="Secure. Fast. Open.", font=("Segoe UI", 10), fg="#e3f2fd", bg=COLOR_PRIMARY).pack()

        content = tk.Frame(top, bg="white", padx=15, pady=15)
        content.pack(fill=tk.BOTH, expand=True)
        
        txt_scroll = scrolledtext.ScrolledText(content, width=50, height=10, font=("Segoe UI", 10), 
                                               bg="white", bd=0, wrap=tk.WORD)
        txt_scroll.pack(fill=tk.BOTH, expand=True)
        txt_scroll.insert(tk.END, about_text)
        txt_scroll.tag_configure("center", justify='center')
        txt_scroll.tag_add("center", "1.0", "end")
        txt_scroll.configure(state='disabled', cursor="arrow")

        tk.Button(top, text="Close", bg="#e0e0e0", bd=0, padx=20, pady=5, command=top.destroy).pack(pady=10)

    def setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=[15, 5])
        s.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", COLOR_PRIMARY)])

    def check_local_folders(self):
        for p in [self.base_dir, self.forti_dir, self.ipsec_dir, self.net_dir]:
            if not os.path.exists(p): os.makedirs(p)

    def log_message(self, m, l="INFO"):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            self.log_text.insert(tk.END, f"[{t}] {m}\n", l)
            self.log_text.see(tk.END)
        except: pass

    def set_status(self, s, c):
        try:
            self.status_label.config(text=f"Status: {s}")
            m = {"ready": "#bdbdbd", "working": "#ff9800", "connected": "#4caf50", "error": "#f44336"}
            self.status_canvas.itemconfig(self.status_circle, fill=m.get(c, "#bdbdbd"))
        except: pass

    def get_current_dir(self):
        return self.forti_dir if self.protocol_var.get() == "forti" else self.ipsec_dir

    def update_ui_mode(self):
        try:
            p = self.protocol_var.get()
            self.refresh_profile_list()
            self.editor_conf.delete('1.0', tk.END)
            self.editor_sec.delete('1.0', tk.END)
            if p == "ipsec":
                self.notebook.add(self.tab2_frame, text="  VPN Secrets (.secrets)  ")
                self.btn_get_cert.pack_forget()
            else:
                self.notebook.hide(self.tab2_frame)
                self.btn_get_cert.pack(side=tk.LEFT, padx=(0, 10))
        except: pass

    def refresh_profile_list(self):
        self.file_listbox.delete(0, tk.END)
        d = self.get_current_dir()
        if os.path.exists(d):
            ext = ".conf" if self.protocol_var.get() == "ipsec" else ".vpn"
            for f in sorted(os.listdir(d)):
                if f.endswith(ext): self.file_listbox.insert(tk.END, f.replace(ext, ""))

    def load_selected_profile(self, e):
        sel = self.file_listbox.curselection()
        if not sel: return
        name = self.file_listbox.get(sel[0])
        d = self.get_current_dir()
        p = self.protocol_var.get()
        ext = ".vpn" if p == "forti" else ".conf"
        
        self.editor_conf.delete('1.0', tk.END)
        try:
            with open(os.path.join(d, name + ext), 'r') as f: self.editor_conf.insert(tk.END, f.read())
        except: pass

        if p == "ipsec":
            self.editor_sec.delete('1.0', tk.END)
            try:
                with open(os.path.join(d, name + ".secrets"), 'r') as f: self.editor_sec.insert(tk.END, f.read())
            except: pass
        self.log_message(f"Loaded: {name}")

    def toggle_buttons(self, connected):
        s1 = "disabled" if connected else "normal"
        s2 = "normal" if connected else "disabled"
        self.btn_connect.config(state=s1)
        self.btn_disconnect.config(state=s2)

    def find_ipsec_conn_name(self, fp):
        if not os.path.exists(fp): return None
        with open(fp, 'r') as f:
            for l in f:
                m = re.search(r'^\s*conn\s+([a-zA-Z0-9_-]+)', l)
                if m: return m.group(1)
        return None

    def check_process_running(self, n):
        try:
            subprocess.check_output(["pgrep", "-x", n])
            return True
        except: return False

    def check_ipsec_established(self):
        try:
            r = subprocess.run(["ipsec", "status"], capture_output=True, text=True)
            return "ESTABLISHED" in r.stdout
        except: return False

    def on_ok(self, e, win, res):
        res[0] = e.get()
        win.destroy()

def simple_input(parent, title, prompt):
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("300x120")
    tk.Label(win, text=prompt).pack(pady=10)
    e = tk.Entry(win)
    e.pack(pady=5)
    e.focus_set()
    res = [None]
    def on_confirm():
        res[0] = e.get()
        win.destroy()
    tk.Button(win, text="OK", command=on_confirm).pack(pady=10)
    win.wait_window()
    return res[0]

if __name__ == "__main__":
    root = tk.Tk()
    app = LivConnectApp(root)
    root.mainloop()
