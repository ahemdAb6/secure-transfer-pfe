# 🔒 SecureTransfer - Self-Hosted File Sharing Platform

> **Stage Project** | Secure, Ephemeral, and Private File Sharing "à la WeTransfer".

## 📖 Overview
**SecureTransfer** is a containerized, self-hosted platform designed for securely sharing sensitive documents. Unlike public cloud solutions, this project ensures **Data Sovereignty** by keeping files within the company's infrastructure.

It features **End-to-End Encryption (AES-256)**, **Automatic Malware Scanning**, **Password Protection**, and **Auto-Expiration** logic to comply with privacy standards (GDPR).

---

## 🚀 Key Features

*   **🛡️ Security First:** Files are encrypted using **Fernet (AES-256)** before storage. Even the admin cannot read them without the unique key generated per transfer.
*   **🦠 Antivirus Integration:** Real-time stream scanning using **ClamAV**. Malicious files are rejected immediately before hitting the disk.
*   **🔑 Access Control:** Optional **Password Protection** (hashed via SHA-256) for transfers. The receiver must enter the password to decrypt the file.
*   **⏳ Ephemeral Storage:** Files are automatically purged after a set duration (TTL) or when the download limit is reached.
*   **🚦 Rate Limiting:** Integrated **DDoS protection** limits uploads/downloads per IP address to prevent abuse.
*   **👤 Admin Dashboard:** A hidden administration interface to monitor active files and force-delete content if necessary.
*   **🐳 Fully Dockerized:** Orchestrated via Docker Compose with Nginx as a Secure Reverse Proxy (HTTPS).

---

## 🛠️ Tech Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | Vue.js 3 + Vite | Glassmorphism UI (Single Page App) |
| **Backend** | Python FastAPI | Async API, Encryption Logic, Rate Limiting |
| **Database** | Redis | Metadata storage & Auto-expiration (TTL) |
| **Security** | ClamAV | Antivirus Engine |
| **Proxy** | Nginx | Reverse Proxy & SSL/TLS Termination |
| **DevOps** | Docker Compose | Container Orchestration |

---

## ⚙️ Installation & Setup

### Prerequisites
*   Docker Desktop installed.
*   Git installed.

### Quick Start
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ahemdAb6/secure-transfer-pfe.git
    cd secure-transfer-pfe
    ```

2.  **Run with Docker:**
    ```bash
    docker compose up --build -d
    ```

3.  **Access the App:**
    Open your browser and go to:
    👉 **https://localhost**
    *(Note: You will see a browser warning because we use a Self-Signed Certificate for local development. Click "Advanced" -> "Proceed" to access the secure HTTPS site).*

    > **Important:** Please wait 2-3 minutes on the very first run for ClamAV to update its virus database.

---

## 👨‍💻 Usage Guide

### Sending a File
1.  Drag and drop a file.
2.  Enter your **Sender Email** (Mandatory).
3.  (Optional) Set a **Password** and Expiration time.
4.  Share the generated **Magic Link** or **QR Code**.

### Receiving a File
1.  Open the link or scan the QR Code.
2.  If the file is password-protected, a secure modal will ask for the credentials.
3.  The file is decrypted in the browser and downloaded.

### 🛡️ Admin Portal (Internal Use)
To access the administration dashboard:
1.  Click the **"Admin Portal"** link (or the Copyright text) in the footer.
2.  Enter the Master Key: `admin123`
3.  View active transfers and delete files manually.

---

## 🧪 Security Testing (Proof of Concept)

### 1. Virus Detection Test
To test the antivirus capability, try uploading the standard **EICAR Test File**.
*   **Content:** `X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*`
*   **Expected Result:** The system will reject the file with a `SECURITY ALERT: Virus Detected` message (HTTP 400).

### 2. Encryption Verification
Uploaded files are stored in `backend/uploads/` with a `.enc` extension. Try opening them manually—they will be unreadable (encrypted bytes).

---

## 👤 Author
**Ahmed Bousetta**
*   **Project:** Stage
*   **Year:** 2026