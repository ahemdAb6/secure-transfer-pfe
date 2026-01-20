# 🔒 SecureTransfer - AI-Powered Secure File Sharing

> **PFE Project (Stage de Perfectionnement)** | Developed for **Axelites** | 2026
> **Author:** Ahmed Bousetta | **Institution:** ISET Kélibia

![Status](https://img.shields.io/badge/Status-Operational-green)
![Security](https://img.shields.io/badge/Security-AES--256-blue)
![AI Engine](https://img.shields.io/badge/AI-FineTuned_CodeBERT-purple)

## 📖 Overview
**SecureTransfer** is an enterprise-grade, self-hosted file sharing platform designed for high-security environments. It acts as a private alternative to WeTransfer, ensuring **Data Sovereignty** and **Zero-Trust Security**.

Unlike standard file sharing tools, SecureTransfer employs a **Multi-Layered Security Engine**:
1.  **Antivirus:** Scans binary files for malware using **ClamAV**.
2.  **AI Data Loss Prevention (DLP):** Uses a specialized **Fine-Tuned CodeBERT Model** embedded directly in the backend to detect secrets (API Keys, Passwords, PII) in milliseconds.
3.  **Encryption:** Military-grade **AES-256 (Fernet)** encryption for data at rest.

---

## 🚀 Key Innovation: Embedded AI Architecture

**Why not ChatGPT or Ollama?**
Traditional AI solutions have significant drawbacks for security:
*   **Latency:** Sending data to external LLMs takes 2-5 seconds.
*   **Privacy Risk:** Confidential files leave the server.
*   **Resource Heavy:** Llama 3 requires 8GB+ RAM.

**My Solution: Embedded CodeBERT**
I fine-tuned the `microsoft/codebert-base` model specifically for secret detection and embedded it directly into the Python application.
*   ✅ **Zero Latency:** Scans take **< 0.05s**.
*   ✅ **Absolute Privacy:** Data never leaves the container RAM.
*   ✅ **Offline Capable:** Works without any internet connection.
*   ✅ **Lightweight:** Runs on standard CPU (No GPU required).

---

## 🛡️ Features

### 1. Intelligent Security Core
*   **🤖 AI Data Leak Detection:** Blocks files containing:
    *   Leaked Credentials (AWS Keys, Private Keys).
    *   Hardcoded Passwords.
    *   "CONFIDENTIAL" document markers.
*   **🦠 Real-Time Antivirus:** Integrated with **ClamAV**.
*   **🔐 End-to-End Encryption:** Files are encrypted before saving to disk.

### 2. User Management
*   **Zero-Trust Registration:** New accounts are **PENDING** until Admin approval.
*   **Daily Quotas:** Limits uploads per user to prevent abuse.
*   **Admin Dashboard:** Live analytics of disk usage and file types.

---

## 🛠️ Tech Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | Vue.js 3 + Tailwind CSS | Responsive, Modern UI |
| **Backend** | Python FastAPI | Async API, Rate Limiting |
| **AI Brain** | **CodeBERT (Fine-Tuned)** | Custom Security Model (PyTorch/Transformers) |
| **Database** | Redis | High-speed Metadata & Caching |
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
    *   Define your `ADMIN_EMAIL` and `ADMIN_PASS`.

3.  **📥 Download the AI Brain (Crucial Step):**
    *   Because the fine-tuned model is large (~500MB), it is stored externally.
    *   **Download Link:** [https://drive.google.com/file/d/19hJ0iHtaAhDEuYTEWmldlpezjx3sy6-i/view?usp=sharing](https://drive.google.com/file/d/19hJ0iHtaAhDEuYTEWmldlpezjx3sy6-i/view?usp=sharing)
    *   **Action:** Unzip the folder `my_model` and place it inside `backend/`.
    *   *Structure Check:* `backend/my_model/pytorch_model.bin`

4.  **Start the Server:**
    ```bash
    docker-compose up --build -d
    ```

5.  **Access the Application:**
    *   **Web App:** http://localhost
    *   **Swagger API Docs:** http://localhost:8000/docs

---

## 🧪 Security Proof of Concept (Test Files)

### Test 1: Virus Upload
*   **File Content:** (EICAR Test Signature)
*   **Result:** `HTTP 400: VIRUS DETECTED`

### Test 2: Secret Key Leak
*   **File Content:** `AWS_ACCESS_KEY_ID = "AKIA1234567890"`
*   **Result:** `HTTP 400: AI SECURITY ALERT: Sensitive Data Detected`

### Test 3: Safe Resume (CV)
*   **File Content:** A standard PDF Resume (up to 50MB).
*   **Result:** `Success` (Smart Partial Scan checks first 5 pages only).

---

## 👤 Author
**Ahmed Bousetta**
*   **Institution:** ISET Kélibia
*   **Company:** Axelites
*   **Year:** 2026