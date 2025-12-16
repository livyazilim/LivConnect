# LivConnect - Enterprise VPN Manager

**LivConnect** is a lightweight, cross-platform GUI wrapper for managing enterprise VPN connections. It allows users to manage **FortiSSL (OpenFortiVPN)** and **IPsec (StrongSwan)** protocols seamlessly on Linux and macOS.

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey.svg)
![License](https://img.shields.io/badge/License-GPLv3-green.svg)

## 🚀 Features

* **Dual Protocol Support:** Manage FortiSSL and IPsec (IKEv2) connections in one place.
* **Modern GUI:** Clean Tkinter-based interface designed for ease of use.
* **System Tray Integration:** Runs in the background and minimizes to the system tray.
* **Profile Management:** Create, edit, and delete connection profiles (`.vpn`, `.conf`, `.secrets`) directly within the app.
* **Secure Privilege Handling:** Uses `pkexec` (Linux) or `osascript` (macOS) to request root privileges only when establishing a connection.
* **Auto-Cert Detection:** Automatically detects and helps trust self-signed Fortinet certificates.

## 🛠️ Prerequisites

This application is a GUI wrapper. The underlying VPN tools must be installed on your system:

### macOS (via Homebrew)

    brew install openfortivpn strongswan

### Linux (Debian/Ubuntu)

    sudo apt update
    sudo apt install openfortivpn strongswan libstrongswan-standard-plugins strongswan-pki

## 📦 Installation & Usage

1. **Clone the repository:**

        git clone [https://github.com/livyazilim/LivConnect.git](https://github.com/livyazilim/LivConnect.git)
        cd LivConnect

2. **Install Python dependencies:**

        pip install -r requirements.txt

3. **Run the application:**

        python3 LivConnect.py

## 🖥️ How to Use

1. **Create Profile:** Click "Create Profile", select the protocol (Forti/IPsec), and enter your credentials.
2. **Connect:** Select a profile from the sidebar and click **CONNECT**. You will be prompted for your system password (sudo/admin) to initialize the network interface.
3. **Background Mode:** Closing the window minimizes the app to the system tray. Right-click the tray icon to exit or disconnect.

## ⚠️ License

This project is licensed under the **GNU General Public License v3.0**.
See the [LICENSE](LICENSE) file for details.

---
Developed by **Liv Yazılım** © 2025
