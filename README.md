# 🔒 SecureTransfer - AI-Powered Secure File Sharing

> **PFE Project (Stage)** | Developed for **Axelites** | 2026

## 📖 Overview
**SecureTransfer** is an enterprise-grade, self-hosted file sharing platform designed for high-security environments. It acts as a private alternative to WeTransfer, ensuring **Data Sovereignty** and **Zero-Trust Security**.

Unlike standard file sharing tools, SecureTransfer employs a **Multi-Layered Security Engine**:
1.  **Antivirus:** Scans binary files for malware using **ClamAV**.
2.  **AI Data Loss Prevention (DLP):** Uses a local AI Model (**Qwen 2.5**) to read documents and block sensitive data leaks (passwords, confidential keys, internal secrets) *before* they leave the network.
3.  **Encryption:** Military-grade **AES-256** encryption.

---

## 🚀 Key Features

### 🛡️ 1. Intelligent Security Core
*   **🤖 AI Data Leak Detection:** Integrated with **Ollama (Qwen 2.5)**. The system analyzes text content (TXT, PDF) to detect and block:
    *   "CONFIDENTIAL" / "INTERNAL USE ONLY" documents.
    *   Leaked Credentials (API Keys, Passwords).
    *   PII (Personal Identifiable Information) leaks.
    *   *Smart Filtering:* Distinguishes between safe Source Code/CVs and actual security threats.
*   **🦠 Real-Time Antivirus:** Integrated with **ClamAV**. Scans every byte stream; viruses are rejected immediately.
*   **🔐 End-to-End Encryption:** Files are encrypted with **Fernet (AES-256)**. The server *never* stores unencrypted files.

### 👤 2. User Management & Auth
*   **Registration System:** Users can sign up, but accounts remain **PENDING** until Admin approval (Zero-Trust).
*   **Role-Based Access:**
    *   **Users:** Can upload/download based on daily quotas.
    *   **Admins:** Full control over users, files, and server health.
*   **Banning System:** Admins can instantly **BAN** users who violate security policies.

### 📊 3. Advanced Admin Dashboard
*   **Live Analytics:** Monitor Disk Usage, File Type distribution, and User Storage consumption.
*   **Audit Logs:** Track who uploaded what file and when.
*   **User Control:** Approve new registrations or Ban suspicious accounts with one click.

---

## 🛠️ Tech Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | Vue.js 3 + Tailwind CSS | Responsive, Modern UI |
| **Backend** | Python FastAPI | Async API, Security Logic, Rate Limiting |
| **AI Brain** | **Ollama + Qwen 2.5 (0.5B)** | Local LLM for Data Loss Prevention (DLP) |
| **Database** | Redis | High-speed Metadata, Session Mgmt & Caching |
| **Antivirus** | ClamAV | Malware Engine |
| **Infrastructure** | Docker Compose | Container Orchestration |

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

2.  **Configure Environment:**
    *   Create a `.env` file in the root directory.
    *   Define your `ADMIN_EMAIL` and `ADMIN_PASS` (See `.env.example`).

3.  **Start the Server:**
    ```bash
    docker compose up --build -d
    ```

4.  **🧠 Initialize the AI Brain (Critical Step):**
    *The AI model runs locally inside Docker. You must download it once.*
    ```bash
    docker exec -it secure_ai_brain ollama run qwen2.5:0.5b
    ```
    *(Wait for the download to finish, then type `/bye` to exit).*

5.  **Access the Application:**
    *   **Web App:** https://localhost
    *   *(Accept the self-signed certificate warning)*

---

## 👨‍💻 Usage Guide

### 1. Registration (First Time)
1.  Go to **Register**.
2.  Create an account.
3.  **Note:** You cannot log in yet! An **Admin** must approve your account first.

### 2. Admin Approval
1.  Log in with the **Master Admin credentials** (Defined in your `.env` file).
    *   *Default:* Check `docker-compose.yml` or your environment variables.
2.  Go to the **Admin Dashboard**.
3.  Find the new user in the list and click **"APPROVE"**.

### 3. Sending a File
1.  Log in as a User.
2.  Drag & Drop a file.
3.  **The Security Scan runs automatically:**
    *   If a **Virus** is found -> **BLOCKED** 🚨
    *   If **Sensitive Data** (e.g., "CONFIDENTIAL") is found -> **BLOCKED** 🚫
    *   If Safe -> **Encrypted & Uploaded** ✅
4.  Copy the generated **Magic Link**.

---

## 🧪 Security Proof of Concept (Testing)

You can demonstrate the security features using these test files:

### Test 1: Antivirus (ClamAV)
*   Create a file named `virus.txt` with this content (EICAR Test Signature):
    ```text
    X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*
    ```
*   **Result:** `HTTP 400: VIRUS DETECTED`

### Test 2: AI Data Leak Prevention (Ollama)
*   Create a file named `secret_project.txt` with this content:
    ```text
    PROJECT TITAN - CONFIDENTIAL DOCUMENT
    INTERNAL USE ONLY
    
    Database Password:
    admin: SuperSecretPassword123
    ```
*   **Result:** `HTTP 400: AI SECURITY ALERT: Sensitive Data Detected`

### Test 3: Safe File (False Positive Check)
*   Upload a standard `Dockerfile` or a `CV.pdf`.
*   **Result:** `Success` (The AI is trained to ignore Code and Resumes).

---

## 👤 Author
**Ahmed Bousetta**
*   **Institution:** ISET Kélibia
*   **Company:** Axelites
*   **Year:** 2026