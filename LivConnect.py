# © 2025 Liv Yazılım ve Danışmanlık Ltd. Şti.

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import multiprocessing
import subprocess
import shutil
import re
import datetime
import platform
import threading
import json
import time
import sys
import socket
import select
import shlex

if not getattr(sys, 'frozen', False):
    try:
        system_site_packages = subprocess.check_output([sys.executable.replace('python', 'python3'), '-c', 
            'import site; print(site.getsitepackages()[0])']).decode().strip()
        if system_site_packages and system_site_packages not in sys.path:
            sys.path.insert(0, system_site_packages)
    except:
        pass

# Tray Support
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
    
    # xorg backend'de sağ-click menüsü desteği eklemek için subclass oluştur
    class CustomXorgIcon(pystray._xorg.Icon):
        """pystray xorg Icon'u sağ-click handler ile extend et"""
        def __init__(self, *args, **kwargs):
            self.on_right_click = kwargs.pop('on_right_click', None)
            self.on_left_click = kwargs.pop('on_left_click', None)
            super().__init__(*args, **kwargs)
        
        def _on_button_press(self, event):
            """Sağ-click (button 3) ve sol-click (button 1) handler"""
            if event.detail == 3:  # Sağ buton
                if self.on_right_click:
                    self.on_right_click()
            elif event.detail == 1:  # Sol buton
                if self.on_left_click:
                    self.on_left_click()
                else:
                    super()._on_button_press(event)
    
    # pystray.Icon yerine CustomXorgIcon kullancak way bulmalıyız
    # Ancak pystray.Icon zaten belirlenmişse, wrapper oluşturalım
    
    # xorg backend'de menü gösterme sorunu varsa, workaround ekle
    try:
        import pystray._appindicator
        print("AppIndicator backend available")
    except (ImportError, Exception) as e:
        print(f"AppIndicator not available ({e}), using xorg backend")
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
        self.livconnect_auth_type = 'normal'  # Track if profile requires OTP/2FA (livconnect_auth_type=otp) 
        
        # SSH Tunnel State Variables
        self.ssh_tunnel_process = None
        self.ssh_tunnel_active = False
        self.active_ssh_tunnel = None

        # Directories - use hidden folder in home directory
        self.user_home = os.path.expanduser("~")
        self.base_dir = os.path.join(self.user_home, ".livconnect")
        self.forti_dir = os.path.join(self.base_dir, "forti")
        self.ipsec_dir = os.path.join(self.base_dir, "ipsec")
        self.net_dir = os.path.join(self.base_dir, "network_profiles")
        self.ssh_dir = os.path.join(self.base_dir, "ssh_tunnels")
        self.check_local_folders()

        # UI Init
        self.setup_styles()
        self.create_menu_bar()
        self.setup_ui_components()

        self.log_message(f"LivConnect v2.1 initialized on {SYSTEM_OS}.")
        
        # Tray Thread
        self.tray_update_thread_stop = False
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
        
        title_label = tk.Label(header_frame, text="LivConnect", font=("Segoe UI", 18, "bold"), bg=COLOR_SIDEBAR, fg="#1a237e")
        title_label.pack(anchor="w")
        
        # Subtitle altında
        subtitle_label = tk.Label(header_frame, text="by Liv Yazılım ve Danışmanlık", font=("Segoe UI", 8), bg=COLOR_SIDEBAR, fg="#999999")
        subtitle_label.pack(anchor="w")

        # MODULE SELECTION
        mod_frame = tk.LabelFrame(self.sidebar_frame, text="Module Select", bg=COLOR_SIDEBAR, pady=10, padx=5, font=("Segoe UI", 9, "bold"))
        mod_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self.protocol_var = tk.StringVar(value="forti")
        rb_style = {"indicatoron": 0, "bg": "#e3f2fd", "fg": COLOR_TEXT, "font": ("Segoe UI", 10, "bold"), "pady": 6}
        
        tk.Radiobutton(mod_frame, text="FortiSSL VPN", variable=self.protocol_var, value="forti", selectcolor=COLOR_PRIMARY, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)
        tk.Radiobutton(mod_frame, text="IPsec / IKEv2", variable=self.protocol_var, value="ipsec", selectcolor=COLOR_PRIMARY, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)
        tk.Radiobutton(mod_frame, text="Network Manager", variable=self.protocol_var, value="network", selectcolor=COLOR_NETWORK, command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)
        tk.Radiobutton(mod_frame, text="🔐 SSH Tunnel", variable=self.protocol_var, value="ssh", selectcolor="#ff5722", command=self.switch_main_view, **rb_style).pack(fill=tk.X, pady=2)

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

        # -- VIEW 3: SSH TUNNEL --
        self.ssh_view_frame = tk.Frame(self.content_container, bg=COLOR_BG)
        self.setup_ssh_tunnel_ui(self.ssh_view_frame)

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
        """Swaps between VPN Editor, Network Manager, and SSH Tunnel views."""
        mode = self.protocol_var.get()
        
        self.vpn_view_frame.pack_forget()
        self.net_view_frame.pack_forget()
        self.ssh_view_frame.pack_forget()

        if mode == "network":
            # Show Network Manager
            self.net_view_frame.pack(fill=tk.BOTH, expand=True)
            self.vpn_list_container.pack_forget()
            self.vpn_btns_frame.pack_forget()
            # Hide VPN Footer
            self.action_bar.pack_forget()
        elif mode == "ssh":
            # Show SSH Tunnel Manager
            self.ssh_view_frame.pack(fill=tk.BOTH, expand=True)
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

        # Inputs (IP & SUBNET MASK)
        grid_frame = tk.Frame(iface_frame, bg="white")
        grid_frame.pack(fill=tk.X, pady=5, padx=20)
        
        # IP
        tk.Label(grid_frame, text="IP Address:", bg="white").grid(row=0, column=0, padx=5, sticky="e")
        self.ent_iface_ip = tk.Entry(grid_frame, width=15)
        self.ent_iface_ip.grid(row=0, column=1, padx=5)
        self.ent_iface_ip.insert(0, "192.168.1.150")

        # Subnet Mask
        tk.Label(grid_frame, text="Subnet Mask:", bg="white").grid(row=0, column=2, padx=5, sticky="e")
        self.ent_iface_subnet = tk.Entry(grid_frame, width=15)
        self.ent_iface_subnet.grid(row=0, column=3, padx=5)
        self.ent_iface_subnet.insert(0, "255.255.255.0")

        # Gateway
        tk.Label(grid_frame, text="Gateway:", bg="white").grid(row=0, column=4, padx=5, sticky="e")
        self.ent_iface_gw = tk.Entry(grid_frame, width=15)
        self.ent_iface_gw.grid(row=0, column=5, padx=5)
        self.ent_iface_gw.insert(0, "192.168.1.1")

        # DNS
        tk.Label(grid_frame, text="Primary DNS:", bg="white").grid(row=0, column=6, padx=5, sticky="e")
        self.ent_iface_dns = tk.Entry(grid_frame, width=15)
        self.ent_iface_dns.grid(row=0, column=7, padx=5)
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
        
        # Remove Selected Button
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
        self.ent_iface_subnet.config(state=state)
        self.ent_iface_gw.config(state=state)
        self.ent_iface_dns.config(state=state)

    # --- Network Logic (JSON & Execution) ---
    def netmask_to_prefix(self, mask):
        """Converts 255.255.255.0 to 24."""
        try:
            return sum([bin(int(x)).count('1') for x in mask.split('.')])
        except:
            return 24 # Fallback

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
                "ip": "", "subnet": "255.255.255.0", "gateway": "", "dns": "",
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
            "subnet": self.ent_iface_subnet.get(),
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
                
                self.ent_iface_subnet.delete(0, tk.END)
                self.ent_iface_subnet.insert(0, data.get("subnet", ""))
                
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
        """Returns the active NetworkManager connection name (Linux only)."""
        # NetworkManager is Linux-only
        if SYSTEM_OS != 'Linux':
            return None
        
        try:
            # nmcli -t -f NAME,DEVICE connection show --active
            # Returns: Wired connection 1:eth0
            res = subprocess.check_output(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"], text=True, timeout=5)
            if res:
                return res.split('\n')[0].strip() # Return first active connection
        except Exception as e:
            self.log_message(f"Could not get NetworkManager connection: {e}", "WARN")
            return None
        return None

    def get_internal_ip(self):
        """Get the internal (local) IP address of the machine directly."""
        return self.get_internal_ip_direct()

    def get_internal_ip_direct(self):
        """Get the internal (local) IP address of the machine directly."""
        try:
            # Get the primary network interface's IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public DNS server (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip if ip else "N/A"
        except Exception as e:
            return "N/A"

    def get_external_ip(self):
        """Get the external (public) IP address directly."""
        return self.get_external_ip_direct()

    def get_external_ip_direct(self):
        """Get the external (public) IP address by querying an external service."""
        try:
            # Try multiple services in case one is down
            services = [
                "https://api.ipify.org?format=json",
                "https://icanhazip.com",
                "https://ident.me"
            ]
            
            for service in services:
                try:
                    import urllib.request
                    with urllib.request.urlopen(service, timeout=5) as response:
                        data = response.read().decode('utf-8').strip()
                        # If it's JSON, extract the IP
                        if '{' in data:
                            import json
                            data = json.loads(data).get('ip', data)
                        # Validate it looks like an IP
                        if '.' in data and len(data) < 16:
                            return data
                except Exception as e:
                    continue
            
            return "N/A"
        except Exception as e:
            return "N/A"

    def _write_protocol_log(self, protocol, message):
        """Write protocol-specific logs (openforti, ipsec, ssh)"""
        try:
            log_file = os.path.join(self.base_dir, f"{protocol}.log")
            with open(log_file, 'a') as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"Error writing {protocol} log: {str(e)}")

    def _monitor_forti_otp(self):
        """Monitor openfortivpn stdout for OTP/SMS prompts and handle them"""
        try:
            if not self.current_process or not self.current_process.stdout:
                return
            
            import select
            import fcntl
            
            # Store process reference to detect if it gets killed mid-execution
            process_ref = self.current_process
            
            # Set stdout to non-blocking mode
            try:
                flags = fcntl.fcntl(process_ref.stdout, fcntl.F_GETFL)
                fcntl.fcntl(process_ref.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            except:
                pass
            
            timeout_counter = 0
            max_timeout = 300  # 5 minutes max wait for SMS
            otp_prompt_triggered = False
            buffer = ""
            authenticated_without_otp = False  # Track if we got "Authenticated" without OTP
            gateway_connected_time = None  # Track when gateway connected
            last_output_time = time.time()  # Track last output from process
            
            while process_ref and process_ref.poll() is None and timeout_counter < max_timeout:
                # Safety check: if current_process was changed/cleared, exit
                if self.current_process != process_ref:
                    self.log_message("OTP monitor: Process reference changed, exiting", "WARN")
                    return
                
                # If we detected "Authenticated" → connection complete, no OTP needed
                if authenticated_without_otp:
                    self.log_message("VPN authenticated without OTP prompt. Connection successful.", "INFO")
                    break
                
                try:
                    # Check if data is available on stdout with 2-second select timeout
                    if select.select([process_ref.stdout], [], [], 2)[0]:
                        try:
                            chunk = process_ref.stdout.read(1024)
                            if chunk:
                                buffer += chunk
                                # Process complete lines
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    line = line.strip()
                                    if line:
                                        last_output_time = time.time()  # Update last output time
                                        self.log_message(f"[FortiVPN] {line}", "INFO")
                                        self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {line}")
                                        
                                        # Check for common OTP/SMS prompts
                                        lower_line = line.lower()
                                        # Trigger on 2FA/OTP keywords, but NOT on generic "authentication" or "Authenticated"
                                        is_otp_prompt = any(prompt in lower_line for prompt in ["two-factor", "sms", "otp", "token:", "challenge:"])
                                        is_not_auth_complete = "authenticated." not in lower_line  # Skip "Authenticated." completion message
                                        
                                        if not otp_prompt_triggered and is_otp_prompt and is_not_auth_complete:
                                            self.log_message(f"OTP/SMS Prompt detected: {line}", "WARN")
                                            self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OTP/SMS Prompt detected! Showing dialog...")
                                            
                                            # Ask user for OTP/SMS code
                                            self.root.after(0, self._prompt_for_otp, line)
                                            otp_prompt_triggered = True
                                            # Don't return - continue monitoring for connection success
                                        
                                        # Check if connection was successful
                                        if "authenticated" in lower_line:
                                            # "Authenticated" message received
                                            if self.livconnect_auth_type == 'otp':
                                                # OTP-enabled profile: wait 3 seconds, then show OTP dialog
                                                self.log_message(f"Authenticated detected. OTP profile - waiting 3s for SMS...", "INFO")
                                                time.sleep(3)
                                                if not otp_prompt_triggered:
                                                    self.log_message(f"Showing OTP dialog (3s after Authenticated)", "WARN")
                                                    self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OTP profile: showing SMS dialog after Authenticated")
                                                    self.root.after(0, self._prompt_for_otp, "SMS/OTP Code Required")
                                                    otp_prompt_triggered = True
                                            else:
                                                # Normal profile: no OTP needed
                                                authenticated_without_otp = True
                                                otp_prompt_triggered = True  # Prevent dialog from opening
                                                gateway_connected_time = time.time()  # Record when gateway connected
                                                self.log_message(f"VPN Connection Established (No OTP required)", "INFO")
                                                self.root.after(0, lambda: (
                                                    self.toggle_buttons(True),
                                                    self.set_status(f"Connected: {self.connected_profile_name}", "connected"),
                                                    self.root.update()
                                                ))
                                        elif "connected to gateway" in lower_line or "add route" in lower_line:
                                            # Gateway connected - check if OTP needed
                                            if self.livconnect_auth_type == 'otp' and not otp_prompt_triggered:
                                                # OTP profile: show dialog after gateway connect
                                                self.log_message(f"Gateway connected. OTP profile detected - showing SMS dialog...", "WARN")
                                                self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OTP profile: showing SMS dialog after gateway connect")
                                                self.root.after(0, self._prompt_for_otp, "SMS/OTP Code Required")
                                                otp_prompt_triggered = True
                                            else:
                                                # Normal profile: connection is complete
                                                if not authenticated_without_otp and not otp_prompt_triggered:
                                                    gateway_connected_time = time.time()  # Record when gateway connected
                                                    last_output_time = time.time()  # Reset output timer
                                                self.log_message(f"VPN Connection Established", "INFO")
                                                self.root.after(0, lambda: (
                                                    self.toggle_buttons(True),
                                                    self.set_status(f"Connected: {self.connected_profile_name}", "connected"),
                                                    self.root.update()
                                                ))
                        except (IOError, OSError):
                            # Non-blocking read when no data available
                            pass
                    else:
                        timeout_counter += 1
                        time.sleep(1)
                except Exception as inner_e:
                    self.log_message(f"OTP monitor read error: {str(inner_e)}", "ERROR")
                    break
                    
        except Exception as e:
            self.log_message(f"Error monitoring OTP: {str(e)}", "ERROR")
            self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Monitor error: {str(e)}")

    def _prompt_for_otp(self, prompt_message):
        """Prompt user for OTP/SMS code via Tkinter dialog"""
        try:
            top = tk.Toplevel(self.root)
            top.title("2FA Authentication Required")
            top.geometry("450x260")  # Increased size for all components
            top.configure(bg="white")
            top.resizable(False, False)
            top.attributes('-topmost', True)  # Stay on top
            
            # Header
            header = tk.Frame(top, bg=COLOR_WARNING, pady=10)
            header.pack(fill=tk.X)
            tk.Label(header, text="🔐 SMS/OTP Authentication", font=("Segoe UI", 12, "bold"), fg="white", bg=COLOR_WARNING).pack()
            
            # Message
            msg_frame = tk.Frame(top, bg="white", pady=15)
            msg_frame.pack(fill=tk.X, padx=20)
            tk.Label(msg_frame, text=f"VPN requires OTP authentication:\n{prompt_message}", font=("Segoe UI", 10), bg="white", justify=tk.LEFT).pack(anchor="w")
            
            # OTP Input
            tk.Label(msg_frame, text="Enter OTP/SMS Code:", font=("Segoe UI", 10, "bold"), bg="white").pack(anchor="w", pady=(10, 5))
            otp_entry = tk.Entry(msg_frame, font=("Segoe UI", 12), width=20, show="*")
            otp_entry.pack(anchor="w")
            otp_entry.focus_set()
            
            def send_otp():
                otp_code = otp_entry.get().strip()
                self.log_message(f"[OTP Dialog] Code entered: {len(otp_code)} chars", "INFO")
                
                if not otp_code:
                    messagebox.showwarning("Warning", "Please enter OTP code")
                    return
                
                try:
                    self.log_message(f"[OTP Dialog] Checking process: {self.current_process is not None}, stdin: {self.current_process.stdin if self.current_process else None}", "INFO")
                    
                    if self.current_process and self.current_process.stdin:
                        self.log_message(f"[OTP Dialog] Sending code to stdin", "INFO")
                        self.current_process.stdin.write(otp_code + "\n")
                        self.current_process.stdin.flush()
                        self.log_message(f"OTP code sent to VPN. Closing dialog...", "INFO")
                        self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OTP code submitted by user")
                        top.destroy()  # Close immediately after sending
                    else:
                        self.log_message(f"[OTP Dialog] Process not available!", "ERROR")
                        messagebox.showerror("Error", "VPN process not available")
                except Exception as e:
                    self.log_message(f"Error sending OTP: {str(e)}", "ERROR")
                    messagebox.showerror("Error", f"Failed to send OTP: {str(e)}")
            
            # Buttons
            btn_frame = tk.Frame(top, bg="white", pady=10)
            btn_frame.pack(fill=tk.X, padx=20)
            tk.Button(btn_frame, text="Send OTP", bg=COLOR_SUCCESS, fg="white", font=("Segoe UI", 10, "bold"), bd=0, padx=15, pady=8, command=send_otp, cursor="hand2").pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Cancel", bg="#e0e0e0", fg="#333", font=("Segoe UI", 10), bd=0, padx=15, pady=8, command=top.destroy, cursor="hand2").pack(side=tk.LEFT)
            
            # Center dialog on screen
            top.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (top.winfo_width() // 2)
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (top.winfo_height() // 2)
            top.geometry(f"+{x}+{y}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to show OTP prompt: {str(e)}")
            self.log_message(f"Error showing OTP prompt: {str(e)}", "ERROR")

    def apply_current_net_config(self):
        # NetworkManager is Linux-only
        if SYSTEM_OS != 'Linux':
            messagebox.showerror("Error", "Network Manager is only available on Linux. On macOS, please use System Settings.")
            return
        
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
            subnet_input = self.ent_iface_subnet.get() # Get Mask string
            gw = self.ent_iface_gw.get()
            dns = self.ent_iface_dns.get()
            
            # Convert Mask to Prefix (if not already)
            if "." in subnet_input:
                prefix = self.netmask_to_prefix(subnet_input)
            else:
                prefix = subnet_input # Fallback if user typed 24

            # Combine for nmcli
            full_ip = f"{ip}/{prefix}"
            
            # Set Manual
            commands.append(f"nmcli con mod '{conn_name}' ipv4.method manual")
            commands.append(f"nmcli con mod '{conn_name}' ipv4.addresses {full_ip}")
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
        def callback(icon=None, item=None):
            try:
                self.connect_vpn_from_tray(profile_name, protocol)
            except Exception as e:
                print(f"Tray action error: {e}")
        return callback

    def _tray_check_closure(self, profile_name):
        def callback(item=None):
            return self.connected_profile_name == profile_name
        return callback

    def _tray_ssh_action_closure(self, profile_name):
        """Closure for SSH tunnel tray menu actions"""
        def callback(icon=None, item=None):
            try:
                self.root.after(0, lambda pn=profile_name: self._connect_ssh_tunnel_tray(pn))
            except Exception as e:
                import traceback
                print(f"Tray SSH action error: {e}")
                traceback.print_exc()
        return callback

    def connect_ssh_tunnel_from_tray(self, profile_name):
        """Connect SSH tunnel from tray menu"""
        self.root.after(0, lambda: self._connect_ssh_tunnel_tray(profile_name))

    def _connect_ssh_tunnel_tray(self, profile_name):
        """Actually connect SSH tunnel (called from main thread)"""
        try:
            if self.ssh_tunnel_active:
                messagebox.showwarning("Status", "SSH tunnel already active. Disconnect first.")
                return
            
            # Load profile
            path = os.path.join(self.ssh_dir, profile_name + ".json")
            if not os.path.exists(path):
                messagebox.showerror("Error", f"SSH profile not found: {profile_name}")
                return
            
            with open(path, 'r') as f:
                profile = json.load(f)
            
            # Set UI fields from profile
            if hasattr(self, 'ssh_profile_combo') and self.ssh_profile_combo is not None:
                self.ssh_profile_combo.set(profile_name)
            
            if hasattr(self, 'ssh_host_entry') and self.ssh_host_entry is not None:
                self.ssh_host_entry.delete(0, tk.END)
                self.ssh_host_entry.insert(0, profile.get("host", ""))
            
            if hasattr(self, 'ssh_port_entry') and self.ssh_port_entry is not None:
                self.ssh_port_entry.delete(0, tk.END)
                self.ssh_port_entry.insert(0, profile.get("port", "22"))
            
            if hasattr(self, 'ssh_user_entry') and self.ssh_user_entry is not None:
                self.ssh_user_entry.delete(0, tk.END)
                self.ssh_user_entry.insert(0, profile.get("user", ""))
            
            if hasattr(self, 'ssh_auth_var') and self.ssh_auth_var is not None:
                auth_type = profile.get("auth_type", "password")
                self.ssh_auth_var.set(auth_type)
            
            if hasattr(self, 'ssh_pass_entry') and self.ssh_pass_entry is not None:
                self.ssh_pass_entry.delete(0, tk.END)
                self.ssh_pass_entry.insert(0, profile.get("password", ""))
            
            if hasattr(self, 'ssh_key_entry') and self.ssh_key_entry is not None:
                self.ssh_key_entry.delete(0, tk.END)
                self.ssh_key_entry.insert(0, profile.get("key_file", ""))
            
            # Switch to SSH module if UI available
            if hasattr(self, 'protocol_var') and self.protocol_var is not None:
                self.protocol_var.set("ssh")
                self.switch_main_view()
            
            # Start tunnel
            self.start_ssh_tunnel()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect SSH tunnel: {str(e)}")
            import traceback
            self.log_message(f"Error connecting SSH tunnel: {str(e)}\n{traceback.format_exc()}", "ERROR")
            # Show window
            self.root.after(100, self._restore_window)
            
            # Start tunnel
            self.root.after(200, self.start_ssh_tunnel)
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect SSH tunnel: {str(e)}")
            self.log_message(f"Error connecting SSH tunnel from tray: {str(e)}", "ERROR")

    def show_ssh_manager_from_tray(self):
        """Show SSH manager from tray"""
        self.root.after(0, lambda: self._show_ssh_manager_tray())

    def _show_ssh_manager_tray(self):
        """Actually show SSH manager (called from main thread)"""
        # Switch to SSH module
        self.protocol_var.set("ssh")
        self.switch_main_view()
        
        # Show window
        self._restore_window()

    def disconnect_ssh_tunnel_from_tray(self):
        """Disconnect SSH tunnel from tray menu"""
        if not self.ssh_tunnel_active:
            messagebox.showwarning("Status", "SSH tunnel not active")
            return
        
        try:
            self.stop_ssh_tunnel()
            messagebox.showinfo("Success", "SSH tunnel disconnected")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to disconnect SSH tunnel: {str(e)}")
            self.log_message(f"Error disconnecting SSH tunnel from tray: {str(e)}", "ERROR")

    def build_tray_menu(self):
        menu_items = []
        # Sol-click: window açılır, sağ-click: bu menü açılır
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

        # SSH Tunnel
        ssh_subs = []
        ssh_status_label = "SSH Tunnel"
        if self.ssh_tunnel_active:
            ssh_status_label = f"🔐 SSH Tunnel (Connected)"
        if os.path.exists(self.ssh_dir):
            for f in sorted(os.listdir(self.ssh_dir)):
                if f.endswith(".json"):
                    name = f[:-5]
                    checked = lambda n=name: (self.active_ssh_tunnel == n)
                    ssh_subs.append(pystray.MenuItem(name, self._tray_ssh_action_closure(name), checked=checked))
        if ssh_subs:
            ssh_subs.append(pystray.Menu.SEPARATOR)
            ssh_subs.append(pystray.MenuItem("Disconnect SSH", lambda: self.root.after(0, self.disconnect_ssh_tunnel_from_tray), enabled=self.ssh_tunnel_active))
            menu_items.append(pystray.MenuItem(ssh_status_label, pystray.Menu(*ssh_subs)))

        # IP Information - Load fresh when menu opens
        menu_items.append(pystray.Menu.SEPARATOR)
        internal_ip = self.get_internal_ip_direct()
        external_ip = self.get_external_ip_direct()
        menu_items.append(pystray.MenuItem(f"Internal IP: {internal_ip}", lambda: None, enabled=False))
        menu_items.append(pystray.MenuItem(f"External IP: {external_ip}", lambda: None, enabled=False))
        
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Quit", self.quit_app))
        return pystray.Menu(*menu_items)

    def init_tray_icon(self):
        # Debug log dosyası
        debug_log = os.path.join(self.base_dir, "tray_debug.log")
        
        def log_debug(msg):
            with open(debug_log, 'a') as f:
                f.write(f"[{datetime.datetime.now()}] {msg}\n")
            print(msg)
        
        log_debug("=== Starting tray initialization ===")
        
        image = self.create_tray_image()
        try:
            menu = self.build_tray_menu()
            log_debug(f"Menu created successfully with items")
        except Exception as e:
            log_debug(f"Menu build error: {e}")
            import traceback
            log_debug(traceback.format_exc())
            menu = pystray.Menu(pystray.MenuItem("Quit", self.quit_app))
        
        # Tray ikonunu oluştur - menü parametresi ile
        try:
            # xorg backend ise CustomXorgIcon kullan
            if 'xorg' in pystray.Icon.__module__.lower():
                self.tray_icon = CustomXorgIcon(
                    "LivConnect", 
                    image, 
                    "LivConnect VPN - Left-click to open, Right-click for menu", 
                    menu=menu,
                    on_left_click=self.show_window_from_tray,
                    on_right_click=self.show_tray_context_menu
                )
                log_debug("Tray icon created with CustomXorgIcon (left & right-click handlers enabled)")
            else:
                self.tray_icon = pystray.Icon(
                    "LivConnect", 
                    image, 
                    "LivConnect VPN - Right-click for menu", 
                    menu=menu
                )
                log_debug("Tray icon created with standard pystray.Icon")
        except Exception as e:
            log_debug(f"Tray icon creation error: {e}")
            import traceback
            log_debug(traceback.format_exc())
            return
        
        log_debug(f"Tray icon backend: {type(self.tray_icon).__module__}")
        
        try:
            log_debug("Running tray icon...")
            self.tray_icon.run()
        except Exception as e:
            log_debug(f"Tray icon run error: {e}")
            import traceback
            log_debug(traceback.format_exc())

    def update_tray_menu(self):
        if hasattr(self, 'tray_icon') and self.tray_icon.visible:
            try:
                self.tray_icon.menu = self.build_tray_menu()
            except: pass

    def connect_vpn_from_tray(self, profile_name, protocol):
        self.root.after(0, lambda: self.connect_vpn(profile_name, protocol))

    def disconnect_vpn_from_tray(self, icon=None, item=None):
        try:
            self.root.after(0, self.disconnect_vpn)
        except Exception as e:
            print(f"Disconnect tray error: {e}")

    def show_window_from_tray(self, icon=None, item=None):
        try:
            # Show LivConnect window (callable from left-click)
            self.root.after(0, self._restore_window)
        except Exception as e:
            print(f"Show window tray error: {e}")

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        try: self.root.focus_force()
        except: pass
        self.is_minimized = False

    def show_tray_context_menu(self, x=None, y=None):
        """Tray context menüsünü Tkinter popup menu'yle göster"""
        if x is None or y is None:
            # İmleçin konumunu al
            try:
                x = self.root.winfo_pointerx()
                y = self.root.winfo_pointery()
            except:
                x = 100
                y = 100
        
        # Tray menüsü
        tray_menu = tk.Menu(self.root, tearoff=0, bg=COLOR_SIDEBAR, fg=COLOR_TEXT)
        tray_menu.add_command(label="Show LivConnect", command=self._restore_window)
        tray_menu.add_separator()
        
        # Disconnect seçeneği
        lbl = "Disconnect"
        if self.connected_profile_name:
            lbl = f"Disconnect ({self.connected_profile_name})"
        if self.connected_profile_name:
            tray_menu.add_command(label=lbl, command=self.disconnect_vpn)
        else:
            tray_menu.add_command(label=lbl, state="disabled")
        
        tray_menu.add_separator()
        
        # FortiSSL submenu
        if os.path.exists(self.forti_dir):
            forti_files = [f[:-4] for f in sorted(os.listdir(self.forti_dir)) if f.endswith(".vpn")]
            if forti_files:
                forti_submenu = tk.Menu(tray_menu, tearoff=0, bg=COLOR_SIDEBAR, fg=COLOR_TEXT)
                for name in forti_files:
                    forti_submenu.add_command(
                        label=name, 
                        command=lambda n=name: self.connect_vpn(n, "forti")
                    )
                tray_menu.add_cascade(label="FortiSSL", menu=forti_submenu)
        
        # IPsec submenu
        if os.path.exists(self.ipsec_dir):
            ipsec_files = [f[:-5] for f in sorted(os.listdir(self.ipsec_dir)) if f.endswith(".conf")]
            if ipsec_files:
                ipsec_submenu = tk.Menu(tray_menu, tearoff=0, bg=COLOR_SIDEBAR, fg=COLOR_TEXT)
                for name in ipsec_files:
                    ipsec_submenu.add_command(
                        label=name,
                        command=lambda n=name: self.connect_vpn(n, "ipsec")
                    )
                tray_menu.add_cascade(label="IPsec", menu=ipsec_submenu)
        
        # SSH Tunnel submenu
        if os.path.exists(self.ssh_dir):
            ssh_files = [f[:-5] for f in sorted(os.listdir(self.ssh_dir)) if f.endswith(".json")]
            if ssh_files:
                ssh_submenu = tk.Menu(tray_menu, tearoff=0, bg=COLOR_SIDEBAR, fg=COLOR_TEXT)
                for name in ssh_files:
                    ssh_submenu.add_command(
                        label=name,
                        command=lambda n=name: self.connect_ssh_tunnel_from_tray(n)
                    )
                ssh_submenu.add_separator()
                ssh_submenu.add_command(label="Disconnect SSH", command=self.disconnect_ssh_tunnel_from_tray, state="normal" if self.ssh_tunnel_active else "disabled")
                ssh_status = "🔐 SSH Tunnel (Connected)" if self.ssh_tunnel_active else "🔐 SSH Tunnel"
                tray_menu.add_cascade(label=ssh_status, menu=ssh_submenu)
        
        # IP Information - Load fresh when menu opens
        tray_menu.add_separator()
        internal_ip = self.get_internal_ip_direct()
        external_ip = self.get_external_ip_direct()
        tray_menu.add_command(label=f"Internal IP: {internal_ip}", state="disabled")
        tray_menu.add_command(label=f"External IP: {external_ip}", state="disabled")
        
        tray_menu.add_separator()
        tray_menu.add_command(label="Quit", command=self.quit_app)
        
        # Menüyü göster
        try:
            tray_menu.tk_popup(x, y)
        except:
            pass

    def on_closing(self):
        if HAS_TRAY:
            self.root.withdraw()
            if not self.is_minimized:
                try: self.tray_icon.notify("LivConnect is minimized to tray.", "LivConnect")
                except: pass
                self.is_minimized = True
        else:
            if messagebox.askokcancel("Quit", "Exit LivConnect? (VPN will stay active)"):
                self.quit_app()

    def quit_app(self, icon=None, item=None):
        #self.disconnect_vpn()
        self.tray_update_thread_stop = True  # Tray update thread'ini durdur
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
                # Log the connection attempt
                self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to connect: {profile_name}")
                
                if IS_MAC:
                    # macOS: Escape path for AppleScript
                    escaped_path = path.replace('"', '\\"').replace("'", "\\'")
                    safe_cmd = f'openfortivpn -c "{escaped_path}" --set-dns=1 --pppd-use-peerdns=1 --use-resolvconf=1 --otp-prompt="Challenge\\|OTP\\|SMS\\|Enter code" --otp-delay=5'
                    self.current_process = subprocess.Popen(["osascript", "-e", f'do shell script "{safe_cmd}" with administrator privileges'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                else:
                    self.current_process = subprocess.Popen(["pkexec", "openfortivpn", "-c", path, "--set-dns=1", "--pppd-use-peerdns=1", "--use-resolvconf=1", "--otp-prompt=Challenge|OTP|SMS|Enter code", "--otp-delay=5"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                
                self.active_ipsec_conn = None 
                self.connected_profile_name = profile_name 
                
                # Read livconnect_auth_type from profile config (livconnect_auth_type=otp or livconnect_auth_type=normal)
                try:
                    self.livconnect_auth_type = 'normal'  # Default
                    with open(path, 'r') as f:
                        for line in f:
                            if line.strip().startswith('livconnect_auth_type'):
                                self.livconnect_auth_type = line.split('=')[1].strip().lower()
                                self.log_message(f"Profile livconnect_auth_type: {self.livconnect_auth_type}", "INFO")
                                break
                except Exception as e:
                    self.livconnect_auth_type = 'normal'
                
                # Start thread to monitor OTP/SMS prompt
                threading.Thread(target=self._monitor_forti_otp, daemon=True).start()
                
                # Don't set status to "Connected" yet - let the monitoring thread confirm it
                # based on actual openfortivpn output
                self.set_status(f"Connecting: {profile_name}...", "working")
                self.root.update()
                self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Process started, waiting for gateway response...")
                self.is_connecting = False
            except Exception as e:
                self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection error: {str(e)}")
                self.set_status("Error", "error")
                self.log_message(str(e), "ERROR")
                self.toggle_buttons(False)  # Re-enable connect button on error
                self.root.update()
                self.is_connecting = False

        elif protocol == "ipsec":
            conf_path = os.path.join(current_dir, profile_name + ".conf")
            conn_name = self.find_ipsec_conn_name(conf_path)
            
            if not conn_name: 
                self.is_connecting = False
                self.log_message("Connection name not found.", "ERROR")
                self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection name not found: {profile_name}")
                return
            
            # Log the connection attempt
            self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Attempting to connect: {profile_name} (conn: {conn_name})")
            
            # Toplu ipsec komutlarını tek seferde çalıştır - şifre 1 kez soruluyor
            combined_cmd = ["sh", "-c", f"ipsec update && ipsec up {conn_name}"]
            res = self.run_as_root(combined_cmd)
            
            if res and res.returncode == 0:
                self.current_process = None 
                self.active_ipsec_conn = conn_name
                self.connected_profile_name = profile_name 
                self.set_status(f"Connected: {profile_name}", "connected")
                self.log_message("Connection Established", "INFO")
                self.toggle_buttons(True)
                self.root.update()
                self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Successfully connected: {profile_name}")
                self.is_connecting = False
            else:
                self.set_status("Error", "error")
                if res:
                    self.log_message(res.stderr + res.stdout, "ERROR")
                    self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection error: {res.stderr + res.stdout}")
                self.toggle_buttons(False)  # Re-enable connect button on error
                self.root.update()
                self.is_connecting = False
        
        self.is_connecting = False
        self.update_tray_menu()
    def disconnect_vpn(self):
        """Terminates the VPN connection forcefully and with proper privileges."""
        self.log_message("Sending disconnect command...", "WARN")
        
        try:
            # Log the disconnection attempt
            if self.connected_profile_name:
                current_protocol = "openforti" if not self.active_ipsec_conn else "ipsec"
                self._write_protocol_log(current_protocol, f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnecting: {self.connected_profile_name}")
            
            if IS_MAC:
                # macOS: Use osascript to send a privileged pkill -9 command
                cmd = '/usr/bin/pkill -9 openfortivpn'
                subprocess.run(["osascript", "-e", f'do shell script "{cmd}" with administrator privileges'])
                if hasattr(self, 'active_ipsec_conn') and self.active_ipsec_conn:
                    ipsec_cmd = f'ipsec down {self.active_ipsec_conn}'
                    subprocess.run(["osascript", "-e", f'do shell script "{ipsec_cmd}" with administrator privileges'])
                    self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnected successfully")
                    self.active_ipsec_conn = None
            else:
                # Linux: Toplu komut - şifre sadece 1 kez soruluyor
                if hasattr(self, 'active_ipsec_conn') and self.active_ipsec_conn:
                    # IPsec aktif ise: pkill + ipsec down toplu yapılır
                    combined_cmd = ["sh", "-c", f"pkill -9 openfortivpn; ipsec down {self.active_ipsec_conn}"]
                    self.run_as_root(combined_cmd)
                    self._write_protocol_log("ipsec", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnected successfully")
                    self.active_ipsec_conn = None
                else:
                    # Sadece FortiVPN açık ise
                    subprocess.run(["pkexec", "pkill", "-9", "openfortivpn"])
                    self._write_protocol_log("openforti", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnected successfully")

            # Clean up the Python process object if it exists
            if hasattr(self, 'current_process') and self.current_process:
                try:
                    # Use kill() instead of terminate() for a non-catchable signal
                    self.current_process.kill()
                except:
                    pass
                self.current_process = None

            # Update UI state to reflect the disconnection
            self.connected_profile_name = None
            self.set_status("Ready", "ready")
            self.toggle_buttons(False)
            self.root.update()
            self.update_tray_menu()
            self.log_message("VPN process terminated.", "INFO")
            
        except Exception as e:
            self.log_message(f"Disconnection error: {str(e)}", "ERROR")
            self.toggle_buttons(False)
            self.root.update()
            
    def monitor_vpn_status(self):
        if self.is_connecting:
            self.root.after(3000, self.monitor_vpn_status)
            return

        # Only show buttons as locked if we actually have a confirmed connection
        # (i.e., connected_profile_name is set, not just because process is running)
        if self.connected_profile_name:
            # We have an active connection
            self.toggle_buttons(True)
        else:
            # No active connection confirmed
            self.toggle_buttons(False)
        
        # Update status display based on actual process state
        is_forti_up = self.check_process_running("openfortivpn")
        is_ipsec_up = self.check_ipsec_established()

        if is_forti_up and not self.connected_profile_name:
            # Process running but not our connection - might be stale
            self.set_status("Stale Process Detected", "warning")
        elif is_ipsec_up and not self.connected_profile_name:
            self.set_status("IPsec Process Detected", "warning")
        elif self.connected_profile_name:
            self.set_status(f"Connected: {self.connected_profile_name}", "connected")
        else:
            self.set_status("Ready", "ready")
        

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

# --- LIVCONNECT SETTINGS ---
# livconnect_auth_type = otp   # Set to 'otp' if VPN requires SMS/2FA authentication
                                 # Dialog will show automatically after gateway connect
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
                escaped_path = path.replace('"', '\\"').replace("'", "\\'")
                safe = f'openfortivpn -c "{escaped_path}" 2>&1'
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
        """Run privileged command using pkexec (Linux) or AppleScript (macOS)."""
        try:
            if IS_MAC:
                cmd_str = shlex.join(cmd)
                escaped_cmd = cmd_str.replace('"', '\\"')
                script = f'do shell script "{escaped_cmd}" with administrator privileges'
                return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return subprocess.run(["pkexec", *cmd], capture_output=True, text=True)
        except Exception as exc:
            self.log_message(f"run_as_root failed: {exc}", "ERROR")
            return None

    # --- STANDARD HELPERS ---
    def create_menu_bar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        f = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=f)
        f.add_command(label="Settings", command=self.open_settings_window)
        f.add_separator()
        f.add_command(label="Exit", command=self.quit_app)
        
        # Tools menu
        t = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=t)
        t.add_command(label="📋 View Logs Folder", command=self.open_logs_directory)
        t.add_separator()
        t.add_command(label="📝 View OpenForti Logs", command=self.open_openforti_log)
        t.add_command(label="📝 View IPsec Logs", command=self.open_ipsec_log)
        t.add_command(label="📝 View SSH Tunnel Logs", command=self.open_ssh_debug_log)
        
        h = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=h)
        h.add_command(label="About", command=self.show_about_dialog)

    def show_about_dialog(self):
        about_text = (
            "LivConnect\n"
            "Enterprise VPN Manager\n"
            "Version 2.1\n\n"
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

    def open_logs_directory(self):
        """Default text editor ile logs klasörünü aç"""
        try:
            if SYSTEM_OS == "Darwin":  # macOS
                subprocess.Popen(["open", "-e", self.base_dir])
            elif SYSTEM_OS == "Windows":
                subprocess.Popen(["notepad", self.base_dir])
            else:  # Linux
                # xdg-open klasörü default file manager'da açar
                subprocess.Popen(["xdg-open", self.base_dir])
            self.log_message(f"Opened logs directory: {self.base_dir}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open logs directory: {str(e)}")
            self.log_message(f"Error opening logs directory: {str(e)}", "ERROR")

    def open_openforti_log(self):
        """OpenForti log dosyasını default text editor ile aç"""
        try:
            log_file = os.path.join(self.base_dir, "openforti.log")
            if not os.path.exists(log_file):
                messagebox.showwarning("Warning", f"OpenForti log file not found:\n{log_file}")
                return
            
            if SYSTEM_OS == "Darwin":  # macOS
                subprocess.Popen(["open", "-a", "TextEdit", log_file])
            elif SYSTEM_OS == "Windows":
                subprocess.Popen(["notepad", log_file])
            else:  # Linux
                subprocess.Popen(["xdg-open", log_file])
            self.log_message(f"Opened OpenForti log: {log_file}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open OpenForti log: {str(e)}")
            self.log_message(f"Error opening OpenForti log: {str(e)}", "ERROR")

    def open_ipsec_log(self):
        """IPsec log dosyasını default text editor ile aç"""
        try:
            log_file = os.path.join(self.base_dir, "ipsec.log")
            if not os.path.exists(log_file):
                messagebox.showwarning("Warning", f"IPsec log file not found:\n{log_file}")
                return
            
            if SYSTEM_OS == "Darwin":  # macOS
                subprocess.Popen(["open", "-a", "TextEdit", log_file])
            elif SYSTEM_OS == "Windows":
                subprocess.Popen(["notepad", log_file])
            else:  # Linux
                subprocess.Popen(["xdg-open", log_file])
            self.log_message(f"Opened IPsec log: {log_file}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open IPsec log: {str(e)}")
            self.log_message(f"Error opening IPsec log: {str(e)}", "ERROR")

    def open_ssh_debug_log(self):
        """SSH Tunnel log dosyasını default text editor ile aç"""
        try:
            log_file = os.path.join(self.base_dir, "ssh.log")
            if not os.path.exists(log_file):
                messagebox.showwarning("Warning", f"SSH Tunnel log file not found:\n{log_file}")
                return
            
            if SYSTEM_OS == "Darwin":  # macOS
                subprocess.Popen(["open", "-a", "TextEdit", log_file])
            elif SYSTEM_OS == "Windows":
                subprocess.Popen(["notepad", log_file])
            else:  # Linux
                subprocess.Popen(["xdg-open", log_file])
            self.log_message(f"Opened SSH Tunnel log: {log_file}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open SSH Tunnel log: {str(e)}")
            self.log_message(f"Error opening SSH Tunnel log: {str(e)}", "ERROR")

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

    # -------------------------------------------------------------------------
    # SSH TUNNEL UI SETUP
    # -------------------------------------------------------------------------
    def setup_ssh_tunnel_ui(self, parent):
        """Setup SSH Tunnel interface in the tab"""
        parent.configure(bg="white")
        
        # Header
        header = tk.Frame(parent, bg="white", pady=10)
        header.pack(fill=tk.X, padx=10)
        tk.Label(header, text="SSH Tunnel Manager", font=("Segoe UI", 14, "bold"), fg="#1976d2", bg="white").pack(side=tk.LEFT)
        
        # Profile Selection Frame
        prof_frame = tk.LabelFrame(parent, text="Profiles", bg="white", padx=10, pady=10, font=("Segoe UI", 9, "bold"))
        prof_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(prof_frame, text="Select Profile:", bg="white").pack(side=tk.LEFT, padx=5)
        self.ssh_profile_combo = ttk.Combobox(prof_frame, width=25, state="readonly")
        self.ssh_profile_combo.pack(side=tk.LEFT, padx=5)
        self.ssh_profile_combo.bind("<<ComboboxSelected>>", self.load_ssh_profile)
        
        tk.Button(prof_frame, text="➕ New", bg="#e0e0e0", command=self.create_ssh_profile, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(prof_frame, text="💾 Save", bg="#c8e6c9", command=self.save_ssh_profile, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(prof_frame, text="🗑️ Delete", bg="#ffcdd2", command=self.delete_ssh_profile, cursor="hand2").pack(side=tk.LEFT, padx=2)
        
        # SSH Connection Settings
        conn_frame = tk.LabelFrame(parent, text="Connection Settings", bg="white", padx=15, pady=10, font=("Segoe UI", 9, "bold"))
        conn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Row 1: Host & Port
        r1 = tk.Frame(conn_frame, bg="white")
        r1.pack(fill=tk.X, pady=3)
        tk.Label(r1, text="SSH Host:", bg="white", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_host_entry = tk.Entry(r1, width=25, font=("Segoe UI", 10))
        self.ssh_host_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(r1, text="Port:", bg="white", width=8, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_port_entry = tk.Entry(r1, width=8, font=("Segoe UI", 10))
        self.ssh_port_entry.insert(0, "22")
        self.ssh_port_entry.pack(side=tk.LEFT, padx=5)
        
        # Row 2: Username & Auth Type
        r2 = tk.Frame(conn_frame, bg="white")
        r2.pack(fill=tk.X, pady=3)
        tk.Label(r2, text="SSH User:", bg="white", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_user_entry = tk.Entry(r2, width=25, font=("Segoe UI", 10))
        self.ssh_user_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(r2, text="Auth:", bg="white", width=8, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_auth_var = tk.StringVar(value="password")
        auth_combo = ttk.Combobox(r2, textvariable=self.ssh_auth_var, values=["password", "key"], width=10, state="readonly")
        auth_combo.pack(side=tk.LEFT, padx=5)
        auth_combo.bind("<<ComboboxSelected>>", self.toggle_ssh_auth_fields)
        
        # Row 3: Password / Key File
        r3 = tk.Frame(conn_frame, bg="white")
        r3.pack(fill=tk.X, pady=3)
        tk.Label(r3, text="Password:", bg="white", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_pass_entry = tk.Entry(r3, width=25, show="●", font=("Segoe UI", 10))
        self.ssh_pass_entry.pack(side=tk.LEFT, padx=5)
        
        # Row 4: Key File (hidden by default)
        r4 = tk.Frame(conn_frame, bg="white")
        r4.pack(fill=tk.X, pady=3)
        tk.Label(r4, text="Key File:", bg="white", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_key_entry = tk.Entry(r4, width=25, font=("Segoe UI", 10))
        self.ssh_key_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(r4, text="Browse", bg="#e3f2fd", command=self.browse_ssh_key, cursor="hand2").pack(side=tk.LEFT, padx=2)
        
        # Hide key file row initially
        self.ssh_key_row = r4
        r4.pack_forget()
        
        # Tunnel Configuration Frame
        tunnel_frame = tk.LabelFrame(parent, text="Tunnel Configuration", bg="white", padx=15, pady=10, font=("Segoe UI", 9, "bold"))
        tunnel_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Port Forwarding Rules
        tk.Label(tunnel_frame, text="Port Forwarding Rules:", bg="white", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=0, pady=(0, 5))
        
        # Add Port Forward
        pfr = tk.Frame(tunnel_frame, bg="white")
        pfr.pack(fill=tk.X, pady=3)
        tk.Label(pfr, text="Local Port:", bg="white", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_local_port_entry = tk.Entry(pfr, width=10, font=("Segoe UI", 10))
        self.ssh_local_port_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(pfr, text="→", bg="white").pack(side=tk.LEFT)
        tk.Label(pfr, text="Remote Host:", bg="white", width=12, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_remote_host_entry = tk.Entry(pfr, width=20, font=("Segoe UI", 10))
        self.ssh_remote_host_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(pfr, text="Remote Port:", bg="white", width=12, anchor="e").pack(side=tk.LEFT, padx=5)
        self.ssh_remote_port_entry = tk.Entry(pfr, width=10, font=("Segoe UI", 10))
        self.ssh_remote_port_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(pfr, text="Add", bg="#bbdefb", command=self.add_ssh_port_forward, cursor="hand2").pack(side=tk.LEFT, padx=5)
        
        # Port Forwarding List
        list_frame = tk.Frame(tunnel_frame, bg="white")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        tk.Label(list_frame, text="Active Rules:", bg="white", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        
        columns = ("local", "remote_host", "remote_port", "action")
        self.ssh_forward_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=4)
        self.ssh_forward_tree.heading("local", text="Local Port")
        self.ssh_forward_tree.heading("remote_host", text="Remote Host")
        self.ssh_forward_tree.heading("remote_port", text="Remote Port")
        self.ssh_forward_tree.heading("action", text="Action")
        self.ssh_forward_tree.column("local", width=80)
        self.ssh_forward_tree.column("remote_host", width=150)
        self.ssh_forward_tree.column("remote_port", width=80)
        self.ssh_forward_tree.column("action", width=60)
        self.ssh_forward_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.ssh_forward_tree.yview)
        self.ssh_forward_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Remove button
        tk.Button(tunnel_frame, text="Remove Selected Rule", bg="#ffcdd2", command=self.remove_ssh_port_forward, cursor="hand2").pack(pady=5)
        
        # Status & Actions
        status_frame = tk.Frame(parent, bg="white", pady=10)
        status_frame.pack(fill=tk.X, padx=10)
        
        self.ssh_status_canvas = tk.Canvas(status_frame, width=20, height=20, bg="white", highlightthickness=0)
        self.ssh_status_canvas.pack(side=tk.LEFT, padx=5)
        self.ssh_status_circle = self.ssh_status_canvas.create_oval(2, 2, 18, 18, fill="#bdbdbd", outline="")
        
        self.ssh_status_label = tk.Label(status_frame, text="Status: Disconnected", bg="white", font=("Segoe UI", 10))
        self.ssh_status_label.pack(side=tk.LEFT, padx=5)
        
        # Action Buttons
        btn_frame = tk.Frame(parent, bg="white", pady=10)
        btn_frame.pack(fill=tk.X, padx=10)
        
        self.ssh_connect_btn = tk.Button(btn_frame, text="▶ CONNECT TUNNEL", bg=COLOR_SUCCESS, fg="white", font=("Segoe UI", 11, "bold"), bd=0, padx=20, pady=10, command=self.start_ssh_tunnel, cursor="hand2")
        self.ssh_connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.ssh_disconnect_btn = tk.Button(btn_frame, text="■ DISCONNECT TUNNEL", bg=COLOR_DANGER, fg="white", font=("Segoe UI", 11, "bold"), bd=0, padx=20, pady=10, command=self.stop_ssh_tunnel, state="disabled", cursor="hand2")
        self.ssh_disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        self.ssh_terminal_btn = tk.Button(btn_frame, text="🖥️ OPEN TERMINAL", bg="#2196f3", fg="white", font=("Segoe UI", 11, "bold"), bd=0, padx=20, pady=10, command=self.open_ssh_terminal, state="disabled", cursor="hand2")
        self.ssh_terminal_btn.pack(side=tk.LEFT, padx=5)
        
        # Refresh profiles
        self.refresh_ssh_profiles()

    def toggle_ssh_auth_fields(self, event=None):
        """Show/hide password or key file based on auth type"""
        if self.ssh_auth_var.get() == "key":
            self.ssh_pass_entry.pack_forget()
            self.ssh_key_row.pack(fill=tk.X, pady=3)
        else:
            self.ssh_key_row.pack_forget()
            self.ssh_pass_entry.pack(side=tk.LEFT, padx=5)

    def browse_ssh_key(self):
        """Open file dialog to select SSH key"""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(title="Select SSH Key", filetypes=[("PEM files", "*.pem"), ("All files", "*.*")])
        if filename:
            self.ssh_key_entry.delete(0, tk.END)
            self.ssh_key_entry.insert(0, filename)

    def add_ssh_port_forward(self):
        """Add port forwarding rule to the tree"""
        local_port = self.ssh_local_port_entry.get()
        remote_host = self.ssh_remote_host_entry.get()
        remote_port = self.ssh_remote_port_entry.get()
        
        if not all([local_port, remote_host, remote_port]):
            messagebox.showwarning("Validation", "Please fill all port forwarding fields")
            return
        
        try:
            int(local_port)
            int(remote_port)
        except ValueError:
            messagebox.showerror("Error", "Ports must be numeric values")
            return
        
        # Add to tree
        self.ssh_forward_tree.insert("", tk.END, values=(local_port, remote_host, remote_port, "Remove"))
        
        # Clear inputs
        self.ssh_local_port_entry.delete(0, tk.END)
        self.ssh_remote_host_entry.delete(0, tk.END)
        self.ssh_remote_port_entry.delete(0, tk.END)

    def remove_ssh_port_forward(self):
        """Remove selected port forwarding rule"""
        selected = self.ssh_forward_tree.selection()
        for item in selected:
            self.ssh_forward_tree.delete(item)

    def refresh_ssh_profiles(self):
        """Refresh SSH profile list"""
        if not os.path.exists(self.ssh_dir):
            os.makedirs(self.ssh_dir)
        files = [f.replace(".json", "") for f in os.listdir(self.ssh_dir) if f.endswith(".json")]
        self.ssh_profile_combo['values'] = sorted(files)
        if files:
            self.ssh_profile_combo.set(files[0])
            self.load_ssh_profile(None)

    def create_ssh_profile(self):
        """Create new SSH tunnel profile"""
        name = simple_input(self.root, "New SSH Tunnel", "Profile Name:")
        if name:
            path = os.path.join(self.ssh_dir, name + ".json")
            if os.path.exists(path):
                messagebox.showerror("Error", "Profile already exists")
                return
            
            default_profile = {
                "host": "",
                "port": "22",
                "user": "",
                "auth_type": "password",
                "password": "",
                "key_file": "",
                "port_forwards": []
            }
            with open(path, 'w') as f:
                json.dump(default_profile, f, indent=2)
            
            self.refresh_ssh_profiles()
            self.ssh_profile_combo.set(name)
            self.load_ssh_profile(None)
            self.log_message(f"SSH profile created: {name}", "INFO")

    def load_ssh_profile(self, event):
        """Load SSH profile from file"""
        profile_name = self.ssh_profile_combo.get()
        if not profile_name:
            return
        
        path = os.path.join(self.ssh_dir, profile_name + ".json")
        if not os.path.exists(path):
            return
        
        try:
            with open(path, 'r') as f:
                profile = json.load(f)
            
            # Load connection settings
            self.ssh_host_entry.delete(0, tk.END)
            self.ssh_host_entry.insert(0, profile.get("host", ""))
            
            self.ssh_port_entry.delete(0, tk.END)
            self.ssh_port_entry.insert(0, profile.get("port", "22"))
            
            self.ssh_user_entry.delete(0, tk.END)
            self.ssh_user_entry.insert(0, profile.get("user", ""))
            
            auth_type = profile.get("auth_type", "password")
            self.ssh_auth_var.set(auth_type)
            self.toggle_ssh_auth_fields()
            
            self.ssh_pass_entry.delete(0, tk.END)
            self.ssh_pass_entry.insert(0, profile.get("password", ""))
            
            self.ssh_key_entry.delete(0, tk.END)
            self.ssh_key_entry.insert(0, profile.get("key_file", ""))
            
            # Load port forwarding rules
            for item in self.ssh_forward_tree.get_children():
                self.ssh_forward_tree.delete(item)
            
            for rule in profile.get("port_forwards", []):
                self.ssh_forward_tree.insert("", tk.END, values=rule[:3])
            
            self.log_message(f"SSH profile loaded: {profile_name}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load profile: {str(e)}")
            self.log_message(f"Error loading SSH profile: {str(e)}", "ERROR")

    def save_ssh_profile(self):
        """Save current SSH profile"""
        profile_name = self.ssh_profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Save", "Select or create a profile first")
            return
        
        path = os.path.join(self.ssh_dir, profile_name + ".json")
        
        # Collect port forwarding rules
        port_forwards = []
        for item in self.ssh_forward_tree.get_children():
            values = self.ssh_forward_tree.item(item)["values"]
            port_forwards.append(values)
        
        profile = {
            "host": self.ssh_host_entry.get(),
            "port": self.ssh_port_entry.get(),
            "user": self.ssh_user_entry.get(),
            "auth_type": self.ssh_auth_var.get(),
            "password": self.ssh_pass_entry.get(),
            "key_file": self.ssh_key_entry.get(),
            "port_forwards": port_forwards
        }
        
        try:
            with open(path, 'w') as f:
                json.dump(profile, f, indent=2)
            messagebox.showinfo("Success", f"SSH profile saved: {profile_name}")
            self.log_message(f"SSH profile saved: {profile_name}", "INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save profile: {str(e)}")
            self.log_message(f"Error saving SSH profile: {str(e)}", "ERROR")

    def delete_ssh_profile(self):
        """Delete SSH profile"""
        profile_name = self.ssh_profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Delete", "Select a profile to delete")
            return
        
        if messagebox.askyesno("Confirm", f"Delete SSH profile '{profile_name}'?"):
            path = os.path.join(self.ssh_dir, profile_name + ".json")
            try:
                os.remove(path)
                self.refresh_ssh_profiles()
                messagebox.showinfo("Success", "SSH profile deleted")
                self.log_message(f"SSH profile deleted: {profile_name}", "INFO")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete profile: {str(e)}")

    def get_ssh_binary(self):
        """Get path to SSH binary, preferring AppImage/macOS bundled version"""
        # Check if running in macOS app bundle
        if hasattr(sys, 'frozen'):
            if getattr(sys, 'frozen') == 'macosx_app':
                # macOS app bundle - check Contents/MacOS or ../bin
                app_bin = os.path.join(os.path.dirname(sys.executable), 'ssh')
                if os.path.exists(app_bin):
                    return app_bin
                # Also check one level up (typical macOS bundle structure)
                bundle_bin = os.path.join(os.path.dirname(sys.executable), '..', '..', 'bin', 'ssh')
                if os.path.exists(bundle_bin):
                    return os.path.abspath(bundle_bin)
            # Check for PyInstaller AppImage bundled SSH in _MEIPASS
            if hasattr(sys, '_MEIPASS'):
                bundled_ssh = os.path.join(sys._MEIPASS, 'bin', 'ssh')
                if os.path.exists(bundled_ssh):
                    return bundled_ssh
        
        # Fall back to system SSH via which command
        try:
            result = subprocess.run(['which', 'ssh'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return 'ssh'  # Default, will use PATH

    def get_sshpass_binary(self):
        """Get path to sshpass binary, preferring bundled copies when frozen"""
        if hasattr(sys, 'frozen'):
            exec_dir = os.path.dirname(sys.executable)
            candidates = [
                os.path.join(exec_dir, 'sshpass'),
                os.path.join(exec_dir, '..', '..', 'bin', 'sshpass'),
            ]
            if hasattr(sys, '_MEIPASS'):
                candidates.append(os.path.join(sys._MEIPASS, 'sshpass'))
                candidates.append(os.path.join(sys._MEIPASS, 'bin', 'sshpass'))
            for path in candidates:
                if os.path.exists(path):
                    return os.path.abspath(path)
        
        try:
            result = subprocess.run(['which', 'sshpass'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            self.log_message(f"Unable to locate sshpass via which: {e}", "WARN")
        
        return None

    def check_port_open(self, host, port, timeout=0.5):
        """Check if a port is open and accessible - very quick timeout for AppImage"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            return result == 0
        except Exception as e:
            self.log_message(f"Port check error for {host}:{port}: {e}", "WARN")
            return True  # Assume port is open on error (don't block SSH attempt)

    def start_ssh_tunnel(self):
        """Start SSH tunnel with current configuration"""
        if self.ssh_tunnel_active:
            messagebox.showwarning("Status", "SSH tunnel already active")
            return
        
        host = self.ssh_host_entry.get()
        port = self.ssh_port_entry.get()
        user = self.ssh_user_entry.get()
        
        if not all([host, port, user]):
            messagebox.showerror("Validation", "Please fill in SSH host, port, and user")
            return
        
        # Check if port is open before attempting connection
        self.log_message(f"Checking if {host}:{port} is open...", "INFO")
        if not self.check_port_open(host, port):
            messagebox.showerror("Connection Error", 
                f"SSH port {port} on {host} is not accessible.\n\n"
                f"Please verify:\n"
                f"• The host address is correct\n"
                f"• The port number is correct\n"
                f"• SSH service is running on the remote host\n"
                f"• Network connectivity and firewall rules")
            self.log_message(f"Port {port} on {host} is not open", "ERROR")
            return
        
        self.log_message(f"Port {port} on {host} is open", "INFO")
        self._continue_ssh_tunnel(host, port, user)
        
    def _continue_ssh_tunnel(self, host, port, user):
        """Start SSH tunnel using OpenSSH subprocess"""
        
        try:
            # Get SSH binary
            ssh_binary = self.get_ssh_binary()
            
            # Build SSH command
            ssh_cmd = [ssh_binary, "-p", str(port), "-N"]
            
            # SSH options
            ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
            ssh_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
            ssh_cmd.extend(["-o", "ServerAliveInterval=60"])
            ssh_cmd.extend(["-o", "ServerAliveCountMax=3"])
            ssh_cmd.extend(["-o", "PasswordAuthentication=yes"])
            
            # Add port forwarding rules
            for item in self.ssh_forward_tree.get_children():
                values = self.ssh_forward_tree.item(item)["values"]
                local_port = values[0]
                remote_host = values[1]
                remote_port = values[2]
                ssh_cmd.extend(["-L", f"{local_port}:{remote_host}:{remote_port}"])
            
            # Add authentication
            if self.ssh_auth_var.get() == "key":
                key_file = self.ssh_key_entry.get()
                if not key_file or not os.path.exists(key_file):
                    messagebox.showerror("Error", "Key file not found or invalid")
                    return
                ssh_cmd.extend(["-i", key_file])
                ssh_cmd.extend(["-o", "PubkeyAuthentication=yes"])
                self.log_message("Using SSH key authentication", "INFO")
            else:
                # Password auth
                password = self.ssh_pass_entry.get()
                if not password:
                    messagebox.showerror("Validation", "Password is required")
                    return
                self.log_message("Using SSH password authentication", "INFO")
            
            # Start SSH process
            if self.ssh_auth_var.get() == "password":
                password = self.ssh_pass_entry.get()
                # Use sshpass for password authentication
                # Try system sshpass first, then relative path for AppImage
                sshpass_bin = self.get_sshpass_binary()
                if not sshpass_bin:
                    messagebox.showerror("Error", "sshpass not found - cannot use password authentication")
                    return
                self.log_message(f"Using sshpass from: {sshpass_bin}", "DEBUG")
                final_cmd = [sshpass_bin, "-p", password] + ssh_cmd + [f"{user}@{host}"]
            else:
                # Use key authentication
                final_cmd = ssh_cmd + [f"{user}@{host}"]
            
            self.ssh_tunnel_process = subprocess.Popen(
                final_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            self.ssh_tunnel_active = True
            self.active_ssh_tunnel = self.ssh_profile_combo.get()
            
            # Write connection log
            self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SSH tunnel connecting: {self.active_ssh_tunnel}")
            
            # Update UI
            self.update_ssh_status(True)
            if hasattr(self, 'ssh_connect_btn'):
                self.ssh_connect_btn.config(state="disabled")
            if hasattr(self, 'ssh_disconnect_btn'):
                self.ssh_disconnect_btn.config(state="normal")
            if hasattr(self, 'ssh_terminal_btn'):
                self.ssh_terminal_btn.config(state="normal")
            self.root.update()
            
            self.log_message(f"SSH tunnel started: {self.active_ssh_tunnel}", "INFO")
            self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SSH tunnel connected: {self.active_ssh_tunnel}")
            
            # Monitor tunnel in background
            threading.Thread(target=self.monitor_ssh_tunnel, daemon=True).start()
        
        except Exception as e:
            error_msg = f"Failed to start SSH tunnel: {str(e)}"
            messagebox.showerror("Error", error_msg)
            self.log_message(error_msg, "ERROR")
            self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error: {str(e)}")
            self.ssh_tunnel_active = False
            if hasattr(self, 'ssh_connect_btn'):
                self.ssh_connect_btn.config(state="normal")
            if hasattr(self, 'ssh_disconnect_btn'):
                self.ssh_disconnect_btn.config(state="disabled")
            self.root.update()
            self.root.update()

    def stop_ssh_tunnel(self):
        """Stop SSH tunnel"""
        if not self.ssh_tunnel_active:
            messagebox.showwarning("Status", "SSH tunnel not active")
            return
        
        try:
            # Log the disconnection
            if self.active_ssh_tunnel:
                self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnecting: {self.active_ssh_tunnel}")
            
            # Stop subprocess if still active
            if self.ssh_tunnel_process:
                self.ssh_tunnel_process.terminate()
                try:
                    self.ssh_tunnel_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.ssh_tunnel_process.kill()
            
            self.ssh_tunnel_active = False
            self.active_ssh_tunnel = None
            
            # Update UI
            self.update_ssh_status(False)
            self.ssh_connect_btn.config(state="normal")
            self.ssh_disconnect_btn.config(state="disabled")
            self.ssh_terminal_btn.config(state="disabled")
            self.root.update()
            
            self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnected successfully")
            messagebox.showinfo("Success", "SSH tunnel stopped")
            self.log_message("SSH tunnel stopped", "INFO")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop SSH tunnel: {str(e)}")
            self.log_message(f"Error stopping SSH tunnel: {str(e)}", "ERROR")
            self._write_protocol_log("ssh", f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Disconnection error: {str(e)}")
            self.ssh_connect_btn.config(state="normal")
            self.ssh_disconnect_btn.config(state="disabled")
            self.root.update()

    def update_ssh_status(self, connected):
        """Update SSH tunnel status display"""
        if connected:
            self.ssh_status_canvas.itemconfig(self.ssh_status_circle, fill="#4caf50")
            self.ssh_status_label.config(text=f"Status: Connected ({self.active_ssh_tunnel})")
        else:
            self.ssh_status_canvas.itemconfig(self.ssh_status_circle, fill="#bdbdbd")
            self.ssh_status_label.config(text="Status: Disconnected")

    def monitor_ssh_tunnel(self):
        """Monitor SSH tunnel process and detect failures"""
        while self.ssh_tunnel_active:
            if self.ssh_tunnel_process:
                poll_result = self.ssh_tunnel_process.poll()
                
                # Check if process ended
                if poll_result is not None:
                    # Get stdout/stderr for debugging
                    stdout = ""
                    stderr = ""
                    try:
                        if self.ssh_tunnel_process.stdout:
                            stdout = self.ssh_tunnel_process.stdout.read()
                        if self.ssh_tunnel_process.stderr:
                            stderr = self.ssh_tunnel_process.stderr.read()
                    except:
                        pass
                    
                    if stdout:
                        self.log_message(f"SSH stdout: {stdout}", "DEBUG")
                    if stderr:
                        self.log_message(f"SSH stderr: {stderr}", "DEBUG")
                    
                    self.log_message(f"SSH tunnel closed (exit code: {poll_result})", "INFO")
                    self.ssh_tunnel_active = False
                    self.root.after(0, self.on_ssh_tunnel_closed)
                    break
            
            time.sleep(2)

    def on_ssh_tunnel_closed(self):
        """Called when SSH tunnel closes"""
        self.update_ssh_status(False)
        if hasattr(self, 'ssh_connect_btn'):
            self.ssh_connect_btn.config(state="normal")
        if hasattr(self, 'ssh_disconnect_btn'):
            self.ssh_disconnect_btn.config(state="disabled")
        if hasattr(self, 'ssh_terminal_btn'):
            self.ssh_terminal_btn.config(state="disabled")
        
        self.log_message("SSH tunnel closed", "INFO")
        messagebox.showinfo("SSH Tunnel", "SSH tunnel connection closed")


    def open_ssh_terminal(self):
        """Open SSH terminal window using the active tunnel"""
        if not self.ssh_tunnel_active:
            messagebox.showwarning("Status", "SSH tunnel not active. Please connect first.")
            return
        
        host = self.ssh_host_entry.get()
        port = self.ssh_port_entry.get()
        user = self.ssh_user_entry.get()
        
        if not all([host, port, user]):
            messagebox.showerror("Validation", "SSH connection details are incomplete")
            return
        
        # Check if port is open before opening terminal
        self.log_message(f"Checking if {host}:{port} is open...", "INFO")
        if not self.check_port_open(host, port):
            messagebox.showerror("Connection Error", 
                f"SSH port {port} on {host} is not accessible.\n\n"
                f"Terminal cannot connect. Please verify:\n"
                f"• The host address is correct\n"
                f"• The port number is correct\n"
                f"• SSH service is running on the remote host\n"
                f"• Network connectivity and firewall rules")
            self.log_message(f"Port {port} on {host} is not open", "ERROR")
            return
        
        self.log_message(f"Port {port} on {host} is open", "INFO")
        self._open_terminal_window(host, port, user)
    
    def _open_terminal_window(self, host, port, user):
        """Actually open the terminal window"""
        try:
            # Terminal connects to the remote host through the SSH tunnel
            # Use the same connection details from UI
            ssh_cmd_str = f"ssh -p {port} {user}@{host}"
            
            # Open in terminal based on OS
            if SYSTEM_OS == "Linux":
                # Try different terminal emulators
                terminals = [
                    ("gnome-terminal", lambda cmd: ["gnome-terminal", "--", "bash", "-c", cmd]),
                    ("xfce4-terminal", lambda cmd: ["xfce4-terminal", "-e", cmd]),
                    ("konsole", lambda cmd: ["konsole", "-e", cmd]),
                    ("xterm", lambda cmd: ["xterm", "-e", cmd]),
                    ("mate-terminal", lambda cmd: ["mate-terminal", "-x", cmd]),
                    ("lxterm", lambda cmd: ["lxterm", "-e", cmd]),
                ]
                
                terminal_found = False
                for term_name, cmd_builder in terminals:
                    if shutil.which(term_name):
                        cmd_list = cmd_builder(ssh_cmd_str)
                        subprocess.Popen(cmd_list)
                        self.log_message(f"SSH terminal opened: {user}@{host}:{port}", "INFO")
                        terminal_found = True
                        break
                
                if not terminal_found:
                    terminal_names = [t[0] for t in terminals]
                    messagebox.showwarning("Warning", "No terminal emulator found. Tried: " + ", ".join(terminal_names))
            
            elif IS_MAC:
                # macOS - use Terminal.app via AppleScript
                # Properly escape quotes for AppleScript
                escaped_ssh = ssh_cmd_str.replace('"', '\\"').replace("'", "\\'")
                script = f'tell application "Terminal" to do script "{escaped_ssh}"'
                subprocess.Popen(["osascript", "-e", script])
                self.log_message(f"SSH terminal opened: {user}@{host}:{port}", "INFO")
            
            else:
                # Windows - use PuTTY or cmd
                if shutil.which("putty"):
                    putty_cmd = ["putty", f"-P {port}", f"{user}@{host}"]
                    subprocess.Popen(putty_cmd)
                else:
                    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", ssh_cmd_str])
                self.log_message(f"SSH terminal opened: {user}@{host}:{port}", "INFO")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open SSH terminal: {str(e)}")
            self.log_message(f"Error opening SSH terminal: {str(e)}", "ERROR")

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
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = LivConnectApp(root)
    root.mainloop()
