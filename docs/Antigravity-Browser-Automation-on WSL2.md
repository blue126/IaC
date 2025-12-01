# Antigravity Browser Automation on WSL2


## Overview
This guide documents how to enable Antigravity's browser automation tools (`browser_subagent`) to work on Windows Subsystem for Linux 2 (WSL2).


## Problem
Antigravity's browser automation tool requires Chrome to be running with remote debugging enabled on port 9222. However, in WSL2 environments, there's a networking isolation issue:


- Chrome runs on Windows and listens on `127.0.0.1:9222` (Windows localhost)
- Antigravity runs in WSL2 and tries to connect to `127.0.0.1:9222` (WSL localhost)
- These are different network namespaces, so the connection fails with `ECONNREFUSED`


**Error message:**
```
failed to connect to browser via CDP: http://127.0.0.1:9222
CDP port not responsive in 5s: playwright: connect ECONNREFUSED 127.0.0.1:9222
```


## Solution Architecture
The solution uses a two-layer port forwarding approach:


```
┌─────────────────────────────────────────────────────────────┐
│  Antigravity (WSL2)                                         │
│  └─> Connects to 127.0.0.1:9222 (WSL localhost)            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  socat (WSL2)                                               │
│  └─> Forwards WSL 127.0.0.1:9222 → <WSL_GATEWAY_IP>:9222       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Windows Port Proxy                                         │
│  └─> Forwards <WSL_GATEWAY_IP>:9222 → 127.0.0.1:9222 (Windows) │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Chrome (Windows)                                           │
│  └─> Listening on 127.0.0.1:9222                           │
└─────────────────────────────────────────────────────────────┘
```


## One-Time Setup


### 1. Find Your WSL Network Gateway
In WSL, run:
```bash
ip route show | grep -i default | awk '{ print $3}'
```
This will return your Windows host IP (e.g., `<WSL_GATEWAY_IP>`). **Note this IP** - you'll use it in the commands below.


### 2. Configure Windows Port Forwarding
Open **PowerShell as Administrator** on Windows and run:
```powershell
netsh interface portproxy add v4tov4 listenport=9222 listenaddress=<YOUR_WSL_GATEWAY_IP> connectport=9222 connectaddress=127.0.0.1
```
Replace `<YOUR_WSL_GATEWAY_IP>` with the IP from step 1 (e.g., `<WSL_GATEWAY_IP>`).


**Verify it was added:**
```powershell
netsh interface portproxy show all
```


You should see:
```
Listen on ipv4:             Connect to ipv4:
Address         Port        Address         Port
--------------- ----------  --------------- ----------
<WSL_GATEWAY_IP> 9222        127.0.0.1       9222
```


### 3. Configure Windows Firewall
In **PowerShell as Administrator**, run:
```powershell
New-NetFirewallRule -DisplayName "Chrome Remote Debug" -Direction Inbound -LocalPort 9222 -Protocol TCP -Action Allow
```


### 4. Install socat in WSL
In your WSL terminal:
```bash
sudo apt-get update && sudo apt-get install -y socat
```


## Per-Session Setup
Every time you want to use Antigravity's browser automation, you need to run these commands:


### 1. Start Chrome with Remote Debugging
From WSL, run:
```bash
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --remote-debugging-port=9222 --no-first-run --no-default-browser-check &
```


**Note:** Adjust the path if Chrome is installed in a different location.


### 2. Start socat Port Forwarder
In WSL, run:
```bash
socat TCP-LISTEN:9222,fork,reuseaddr TCP:<YOUR_WSL_GATEWAY_IP>:9222 &
```
Replace `<YOUR_WSL_GATEWAY_IP>` with your gateway IP.


### 3. Verify Connection
Test that everything is working:
```bash
curl -s http://127.0.0.1:9222/json/version | jq .
```


You should see Chrome version information in JSON format.


## Usage
Once the setup is complete, Antigravity's browser automation tools will work normally:


```
browser_subagent can now:
- Navigate to URLs
- Take screenshots
- Click elements
- Fill forms
- Record browser sessions
```


## Cleanup
To stop the browser automation setup:


```bash
# Kill socat processes
pkill socat


# Close Chrome (or close it manually from Windows)
```


## Troubleshooting


### Connection Still Fails
1. **Check if Chrome is running:**
   ```powershell
   # In Windows PowerShell
   Get-Process chrome
   ```


2. **Check if port forwarding is active:**
   ```powershell
   # In Windows PowerShell as Admin
   netsh interface portproxy show all
   ```


3. **Check if socat is running:**
   ```bash
   # In WSL
   ps aux | grep socat
   ```


4. **Test direct connection to Windows:**
   ```bash
   # In WSL (replace with your gateway IP)
   curl -s http://<WSL_GATEWAY_IP>:9222/json/version
   ```


### Firewall Issues
If curl to `<WSL_GATEWAY_IP>:9222` times out, the Windows firewall might be blocking it:
```powershell
# In PowerShell as Admin - verify the rule exists
Get-NetFirewallRule -DisplayName "Chrome Remote Debug"
```


### Port Already in Use
If you get "Address already in use" errors:
```bash
# Kill existing socat processes
pkill socat


# Then restart socat
```


## Alternative: WSLg X11 Forwarding
If you prefer not to use this setup, you could potentially run Chrome directly in WSL using WSLg, but this requires:
- Windows 11 or Windows 10 with WSLg support
- Installing Chrome in WSL (not Windows)
- Proper X11 configuration


The port forwarding approach documented here is more reliable and uses the Windows Chrome installation.


## Notes for Antigravity Developers


### Potential Improvements
1. **Auto-detect WSL environment** and provide setup guidance
2. **Allow configuring CDP endpoint** via environment variable:
   ```bash
   export ANTIGRAVITY_CDP_ENDPOINT="http://<WSL_GATEWAY_IP>:9222"
   ```
3. **Auto-setup script** that detects WSL and configures port forwarding
4. **Documentation** in the main Antigravity docs about WSL support


### Technical Details
- The browser tool uses Playwright's CDP (Chrome DevTools Protocol) client
- The CDP endpoint is currently hardcoded to `http://127.0.0.1:9222`
- WSL2 uses a virtualized network adapter with NAT
- The Windows host IP changes between WSL sessions (though rarely)


## Tested Environment
- **OS:** Windows 11 with WSL2 (Ubuntu 24.04)
- **Chrome:** Version 142.0.7444.163
- **socat:** Version 1.8.0.0
- **Antigravity:** Current version as of 2025-11-19


## Credits
Setup documented by user working on web3-game project while implementing admin console with browser automation.


---


**Date:** 2025-11-19  
**Status:** ✅ Tested and Working

# Antigravity Browser Automation on WSL2


## Overview
This guide documents how to enable Antigravity's browser automation tools (`browser_subagent`) to work on Windows Subsystem for Linux 2 (WSL2).


## Problem
Antigravity's browser automation tool requires Chrome to be running with remote debugging enabled on port 9222. However, in WSL2 environments, there's a networking isolation issue:


- Chrome runs on Windows and listens on `127.0.0.1:9222` (Windows localhost)
- Antigravity runs in WSL2 and tries to connect to `127.0.0.1:9222` (WSL localhost)
- These are different network namespaces, so the connection fails with `ECONNREFUSED`


**Error message:**
```
failed to connect to browser via CDP: http://127.0.0.1:9222
CDP port not responsive in 5s: playwright: connect ECONNREFUSED 127.0.0.1:9222
```


## Solution Architecture
The solution uses a two-layer port forwarding approach:


```
┌─────────────────────────────────────────────────────────────┐
│  Antigravity (WSL2)                                         │
│  └─> Connects to 127.0.0.1:9222 (WSL localhost)            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  socat (WSL2)                                               │
│  └─> Forwards WSL 127.0.0.1:9222 → <WSL_GATEWAY_IP>:9222       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Windows Port Proxy                                         │
│  └─> Forwards <WSL_GATEWAY_IP>:9222 → 127.0.0.1:9222 (Windows) │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Chrome (Windows)                                           │
│  └─> Listening on 127.0.0.1:9222                           │
└─────────────────────────────────────────────────────────────┘
```


## One-Time Setup


### 1. Find Your WSL Network Gateway
In WSL, run:
```bash
ip route show | grep -i default | awk '{ print $3}'
```
This will return your Windows host IP (typically something like `192.168.x.x`). **Note this IP** - you'll use it in the commands below. We'll refer to this as `<WSL_GATEWAY_IP>` throughout this guide.


### 2. Configure Windows Port Forwarding
Open **PowerShell as Administrator** on Windows and run:
```powershell
netsh interface portproxy add v4tov4 listenport=9222 listenaddress=<WSL_GATEWAY_IP> connectport=9222 connectaddress=127.0.0.1
```
Replace `<WSL_GATEWAY_IP>` with the IP from step 1.


**Verify it was added:**
```powershell
netsh interface portproxy show all
```


You should see:
```
Listen on ipv4:             Connect to ipv4:
Address         Port        Address         Port
--------------- ----------  --------------- ----------
<WSL_GATEWAY_IP> 9222       127.0.0.1       9222
```


### 3. Configure Windows Firewall
In **PowerShell as Administrator**, run:
```powershell
New-NetFirewallRule -DisplayName "Chrome Remote Debug" -Direction Inbound -LocalPort 9222 -Protocol TCP -Action Allow
```


### 4. Install socat in WSL
In your WSL terminal:
```bash
sudo apt-get update && sudo apt-get install -y socat
```


## Per-Session Setup
Every time you want to use Antigravity's browser automation, you need to run these commands:


### 1. Start Chrome with Remote Debugging
From WSL, run:
```bash
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --remote-debugging-port=9222 --no-first-run --no-default-browser-check &
```


**Note:** Adjust the path if Chrome is installed in a different location.


### 2. Start socat Port Forwarder
In WSL, run:
```bash
socat TCP-LISTEN:9222,fork,reuseaddr TCP:<WSL_GATEWAY_IP>:9222 &
```
Replace `<WSL_GATEWAY_IP>` with your gateway IP from step 1.


### 3. Verify Connection
Test that everything is working:
```bash
curl -s http://127.0.0.1:9222/json/version | jq .
```


You should see Chrome version information in JSON format.


## Usage
Once the setup is complete, Antigravity's browser automation tools will work normally:


```
browser_subagent can now:
- Navigate to URLs
- Take screenshots
- Click elements
- Fill forms
- Record browser sessions
```


## Cleanup
To stop the browser automation setup:


```bash
# Kill socat processes
pkill socat


# Close Chrome (or close it manually from Windows)
```


## Troubleshooting


### Connection Still Fails
1. **Check if Chrome is running:**
   ```powershell
   # In Windows PowerShell
   Get-Process chrome
   ```


2. **Check if port forwarding is active:**
   ```powershell
   # In Windows PowerShell as Admin
   netsh interface portproxy show all
   ```


3. **Check if socat is running:**
   ```bash
   # In WSL
   ps aux | grep socat
   ```


4. **Test direct connection to Windows:**
   ```bash
   # In WSL (replace <WSL_GATEWAY_IP> with your actual gateway IP)
   curl -s http://<WSL_GATEWAY_IP>:9222/json/version
   ```


### Firewall Issues
If curl to `<WSL_GATEWAY_IP>:9222` times out, the Windows firewall might be blocking it:
```powershell
# In PowerShell as Admin - verify the rule exists
Get-NetFirewallRule -DisplayName "Chrome Remote Debug"
```


### Port Already in Use
If you get "Address already in use" errors:
```bash
# Kill existing socat processes
pkill socat


# Then restart socat
```


## Alternative: WSLg X11 Forwarding
If you prefer not to use this setup, you could potentially run Chrome directly in WSL using WSLg, but this requires:
- Windows 11 or Windows 10 with WSLg support
- Installing Chrome in WSL (not Windows)
- Proper X11 configuration


The port forwarding approach documented here is more reliable and uses the Windows Chrome installation.


## Notes for Antigravity Developers


### Potential Improvements
1. **Auto-detect WSL environment** and provide setup guidance
2. **Allow configuring CDP endpoint** via environment variable:
   ```bash
   export ANTIGRAVITY_CDP_ENDPOINT="http://<WSL_GATEWAY_IP>:9222"
   ```
3. **Auto-setup script** that detects WSL and configures port forwarding
4. **Documentation** in the main Antigravity docs about WSL support


### Technical Details
- The browser tool uses Playwright's CDP (Chrome DevTools Protocol) client
- The CDP endpoint is currently hardcoded to `http://127.0.0.1:9222`
- WSL2 uses a virtualized network adapter with NAT
- The Windows host IP changes between WSL sessions (though rarely)


## Tested Environment
- **OS:** Windows 11 with WSL2 (Ubuntu 24.04 LTS)
- **Chrome:** Version 142.x
- **socat:** Version 1.8.x
- **Antigravity:** Current version as of November 2025


## Credits
Setup documented and tested by community member working on a Next.js project with admin console features requiring browser automation.


---


**Status:** ✅ Tested and Working