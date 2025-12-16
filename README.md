# LivConnect - Enterprise Network & VPN Suite

**LivConnect** is a comprehensive, lightweight GUI wrapper for managing enterprise VPN connections and local network configurations. Conceptualized by **Liv Yazılım ve Danışmanlık**, this tool streamlines complex network tasks into a user-friendly interface.

> 🤖 **AI-Augmented Design:** This software was architected and refined with the assistance of Artificial Intelligence, demonstrating the synergy between human expertise and modern AI capabilities.

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey.svg)
![License](https://img.shields.io/badge/License-GPLv3-green.svg)
![Developer](https://img.shields.io/badge/Developer-Liv%20Yazılım-orange.svg)

## 🚀 Features

### 🔐 VPN Management
* **Dual Protocol Support:** Manage **FortiSSL (OpenFortiVPN)** and **IPsec (StrongSwan)** connections in one place.
* **Auto-Cert Detection:** Automatically detects and helps trust self-signed Fortinet certificates.
* **Secure Privilege Handling:** Uses `pkexec` (Linux) or `osascript` (macOS) to request root privileges only when establishing a connection.

### 🌐 Network Manager (IP Changer)
* **Profile-Based Routing:** Save and load different network configurations (e.g., "Office Static", "Home DHCP").
* **IP & DNS Management:** Quickly switch between **Static IP** and **DHCP** modes without touching system files manually.
* **Static Routes:** Easily add or remove persistent static routes for specific subnets.
* **One-Click Apply:** Apply complex network settings (IP, Gateway, DNS, Routes) instantly via `nmcli`.

### 💻 User Experience
* **System Tray Integration:** Runs in the background and minimizes to the system tray for quick access.
* **Modern GUI:** Clean Tkinter-based interface designed for enterprise ease of use.

## 🏢 About the Developer

**LivConnect** is developed by **Liv Yazılım ve Danışmanlık Ltd. Şti.**

We are a technology company focused on producing high-end **Enterprise Solutions**. By combining industry experience with innovative technologies, we ensure business continuity and efficiency for our clients.

* 🏆 **Canias ERP Solution Partner:** We provide specialized consultancy and development services for Canias ERP ecosystems.
* 🚀 **Enterprise Integration:** Expert solutions for complex network structures and software integrations.

## 🛠️ Prerequisites

This application is a GUI wrapper. The underlying tools must be installed on your system:

### macOS (via Homebrew)
~~~bash
brew install openfortivpn strongswan
~~~

### Linux (Debian/Ubuntu/Mint)
Ensure `NetworkManager` is managed via `nmcli` for the IP Changer module to work correctly.
~~~bash
sudo apt update
sudo apt install openfortivpn strongswan libstrongswan-standard-plugins strongswan-pki network-manager
~~~

## 📦 Installation & Usage

1. **Clone the repository:**
   ~~~bash
   git clone [https://github.com/livyazilim/LivConnect.git](https://github.com/livyazilim/LivConnect.git)
   cd LivConnect
   ~~~

2. **Install Python dependencies:**
   ~~~bash
   pip install -r requirements.txt
   ~~~

3. **Run the application:**
   ~~~bash
   python3 LivConnect.py
   ~~~

## 🖥️ How to Use

### VPN Module
1. **Create Profile:** Click "Create Profile", select the protocol (Forti/IPsec), and enter your credentials.
2. **Connect:** Select a profile from the sidebar and click **CONNECT**.
3. **Tray:** Close the window to minimize to the tray. Right-click the icon to disconnect.

### Network Module (IP Changer)
1. **Select Module:** Switch to "Network Manager" from the sidebar.
2. **Configure:** Choose "Manual" to set a Static IP or "Automatic" for DHCP.
3. **Add Routes:** (Optional) Add specific static routes for your corporate intranet.
4. **Save & Apply:** Save as a JSON profile for later use, or click **⚡ APPLY CONFIGURATION** to update your network interface immediately.

## ⚠️ License

This project is licensed under the **GNU General Public License v3.0**.
See the [LICENSE](LICENSE) file for details.

---
**© 2025 Liv Yazılım ve Danışmanlık Ltd. Şti.** *Innovating with Intelligence.*
