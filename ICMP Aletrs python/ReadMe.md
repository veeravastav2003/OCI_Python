# 🚨 VM Reboot Alert System on Oracle Cloud Infrastructure (OCI)

This project provides a **serverless solution** to detect and alert when a **VM is rebooted from the OS level** in OCI using:
- Custom log monitoring
- OCI Functions (Python)
- Notifications via OCI ONS
- OCI Connector Hub integration

---

## 🧩 Features

- ✅ Detects VM reboots using log pattern matching
- ✅ Sends email or push alerts via ONS
- ✅ Fetches VM private IPs dynamically
- ✅ 100% serverless – minimal infrastructure
- ✅ Built for **Linux-based VMs**

---

## 🔧 Architecture Overview

1. **Custom Log Group & Agent Configuration**:
   - Monitors `/var/log/*` for reboot patterns
   - Collects logs using OCI Logging agent

2. **OCI Function (Python)**:
   - Triggered via Connector Hub
   - Parses reboot event, fetches instance private IP
   - Publishes alert message to OCI Notification Topic (ONS)

3. **Connector Hub**:
   - Connects the log search query with the OCI Function

4. **ONS Notification**:
   - Sends alert to subscribed email or webhook

---

