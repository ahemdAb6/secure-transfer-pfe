# 🔒 SecureTransfer - Self-Hosted File Sharing Platform

> **PFE Project** | Secure, Ephemeral, and Private File Sharing "à la WeTransfer".

## 📖 Overview
**SecureTransfer** is a containerized, self-hosted platform designed for securely sharing sensitive documents. Unlike public cloud solutions, this project ensures **Data Sovereignty** by keeping files within the company's infrastructure.

It features **End-to-End Encryption (AES-256)**, **Automatic Malware Scanning**, and **Auto-Expiration** logic to comply with privacy standards (GDPR).

---

## 🚀 Key Features

*   **🛡️ Security First:** Files are encrypted using **Fernet (AES)** before storage. Even the admin cannot read them without the key.
*   **🦠 Antivirus Integration:** Real-time scanning using **ClamAV**. Malicious files are rejected immediately.
*   **⏳ Ephemeral Storage:** Files are automatically deleted after **24 hours** (managed by Redis).
*   **🐳 Fully Dockerized:** One command setup using Docker Compose.
*   **⚡ Modern UI:** Built with **Vue.js 3** for a fast and responsive experience.

---

## 🛠️ Tech Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | Vue.js 3 + Vite | User Interface (Single Page App) |
| **Backend** | Python FastAPI | API, Encryption Logic, File Handling |
| **Database** | Redis | Metadata storage & Auto-expiration (TTL) |
| **Security** | ClamAV | Antivirus Engine |
| **Proxy** | Nginx | Reverse Proxy & Static File Serving |
| **DevOps** | Docker Compose | Orchestration |

---

## ⚙️ Installation & Setup

### Prerequisites
*   Docker Desktop installed.
*   Git installed.

### Quick Start
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/secure-transfer-pfe.git
    cd secure-transfer-pfe
    ```

2.  **Run with Docker:**
    ```bash
    docker compose up --build -d
    ```

3.  **Access the App:**
    Open your browser and go to:
    👉 **http://localhost**

    *(Note: Please wait 2-3 minutes on the first run for ClamAV to update its virus database).*

---

## 🧪 Security Testing (Proof of Concept)

### 1. Virus Detection Test
To test the antivirus capability, try uploading the standard **EICAR Test File**.
*   **Content:** `X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*`
*   **Expected Result:** The system will reject the file with a `SECURITY ALERT: Virus Detected` message.

### 2. Encryption Verification
Uploaded files are stored in `backend/uploads/` with a `.enc` extension. Try opening them manually—they will be unreadable (encrypted).

---

## 👤 Author
**Ahmed Bousetta**
*   **Project:** PFE / Stage Ingénieur
*   **Year:** 2026

---