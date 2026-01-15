import shutil
import os
import uuid
import requests
from fastapi import BackgroundTasks
from pypdf import PdfReader  # <--- MAKE SURE THIS IS HERE
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import json
import io
import threading
import time
import hashlib
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Body
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet
try:
    from dotenv import load_dotenv
    load_dotenv() # Tries to load the .env file
except ImportError:
    # If the library is missing, we just ignore it. 
    # Docker usually injects variables automatically anyway.
    print("⚠️ WARNING: 'python-dotenv' library missing. Using system defaults.")

# ... continue with the rest of your imports ...
# --- SAFE IMPORTS ---
try:
    import redis
except ImportError:
    redis = None
    print("⚠️ WARNING: 'redis' library missing.")

try:
    import clamd
except ImportError:
    clamd = None
    print("⚠️ WARNING: 'clamd' library missing.")


try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
except ImportError:
    def get_remote_address(r): return "127.0.0.1"
    class Limiter:
        def __init__(self, key_func): pass
        def limit(self, limit_value):
            def decorator(func): return func
            return decorator
    class RateLimitExceeded(Exception): pass
    def _rate_limit_exceeded_handler(req, exc): return Response("Busy", status_code=429)

# --- CONFIGURATION ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ADMIN CREDENTIALS (PRO TIP: Use os.getenv in production)
# --- CONFIGURATION ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Use os.getenv to read from the .env file
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@axelites.com") 
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "admin123")


# This enables switching between 'localhost' (testing) and 'redis' (docker)
REDIS_HOST = os.getenv("REDIS_HOST", "redis") 
import os




# Connexion Redis
r = None
if redis:
    try:
        # Use the variable REDIS_HOST here
        r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis Connected")
    except:
        print("⚠️ Redis Connection Failed")
# --- INIT APP ---
app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost",
        "http://localhost"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- HELPERS ---

def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_current_user_email(session_token: str):
    if not session_token or not r: return None
    return r.get(f"session:{session_token}")

def verify_admin(key: str) -> bool:
    """Checks if the key is the Master Pass OR a valid Admin Session"""
    # 1. Master Key Check
    if key == ADMIN_SECRET: return True
    
    # 2. Session Token Check
    if r:
        session_email = r.get(f"session:{key}")
        if session_email == ADMIN_EMAIL:
            return True
            
    return False

def scan_file_for_virus(content: bytes):
    if not clamd: return
    try:
        # Tries to connect to ClamAV container on port 3310
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        if cd.ping() != 'PONG': return 
        scan_result = cd.instream(io.BytesIO(content))
        if scan_result and scan_result['stream'][0] == 'FOUND':
            raise HTTPException(status_code=400, detail=f"VIRUS DETECTED: {scan_result['stream'][1]}")
    except HTTPException as he: raise he
    except Exception: pass
# --- OLLAMA AI CONFIGURATION ---
OLLAMA_URL = "http://ollama:11434/api/generate"
AI_MODEL = "qwen2.5:0.5b"

def scan_with_ollama(content: bytes, filename: str):
    """
    Extracts text (from TXT or PDF) and scans it with AI.
    """
    text_preview = ""

    # --- 1. EXTRACT TEXT BASED ON FILE TYPE ---
    try:
        if filename.endswith(".pdf"):
            # It is a PDF: Read only the first 2 pages
            pdf_file = io.BytesIO(content)
            reader = PdfReader(pdf_file)
            
            if len(reader.pages) > 0:
                text_preview += reader.pages[0].extract_text()
            if len(reader.pages) > 1:
                text_preview += " " + reader.pages[1].extract_text()
        else:
            # It is a Text file
            text_preview = content.decode('utf-8')

    except Exception as e:
        print(f"⚠️ Could not read file text: {e}")
        return "SAFE" 

    # Limit to 1000 characters for Speed (Start + End)
    if len(text_preview) > 1000:
        text_preview = text_preview[:500] + "\n... [SKIPPED] ...\n" + text_preview[-500:]
    else:
        text_preview = text_preview[:1000]

    # --- 2. THE PROMPT (Qwen 2.5) ---
    # --- 3. THE ENTERPRISE PROMPT (Qwen 2.5) ---
    # --- 3. THE "STRICT" ENTERPRISE PROMPT ---
    prompt = f"""
    Analyze this text for Security Breaches.
    
    TEXT:
    "{text_preview}"
    
    INSTRUCTIONS:
    1. **SAFE CONTENT (Allow these):**
       - Resume / CV / Job Application.
       - Source Code / Dockerfile / Configs (UNLESS they contain real passwords).
       - Legal Disclaimers in email footers.
    
    2. **DANGEROUS CONTENT (BLOCK these):**
       - "CONFIDENTIAL" or "INTERNAL USE ONLY" in the **Header** or **Title**.
       - Real Credentials (e.g., 'User: admin', 'Password: ...').
       - Database dumps or private customer lists.

    DECISION LOGIC:
    - Does this contain a SECRET? -> Reply "BLOCK".
    - Is it just code or a CV? -> Reply "SAFE".
    
    OUTPUT:
    Reply with ONE WORD ONLY: "SAFE" or "BLOCK".
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": AI_MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=20)
        
        if response.status_code == 200:
            result = response.json().get("response", "").strip().upper()
            
            # Clean punctuation
            import string
            result_clean = result.translate(str.maketrans('', '', string.punctuation))

            print(f"🔍 ANALYZING: {filename}")
            print(f"🤖 AI RAW OUTPUT: '{result}'")

            # Decision Logic
            if result_clean == "BLOCK" or result_clean.startswith("BLOCK "):
                print(f"🚫 AI VERDICT: BLOCKED")
                # This raises the error to stop the upload immediately
                msg = "⚠️ AI SECURITY ALERT: Sensitive Data Detected."
                raise HTTPException(status_code=400, detail=msg)
            
            # Extra Keyword Safety
            if "CONFIDENTIAL" in result_clean and "NOT CONFIDENTIAL" not in result_clean:
                 print(f"🚫 AI VERDICT: BLOCKED (Keyword Found)")
                 raise HTTPException(status_code=400, detail="⚠️ AI SECURITY ALERT: Confidential Data Found.")
                 
            print(f"✅ AI VERDICT: SAFE")
            return "SAFE"

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Warning: AI Service error: {e}. Allowing file.")
        return "SAFE"
# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = os.getenv("SMTP_EMAIL")       # Reads from .env
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") # Reads from .env

def send_email_notification(to_email: str, subject: str, message: str):
    """
    Sends an email in the background.
    If it fails (bad email), it just logs the error and continues.
    """
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("⚠️ EMAIL SKIPPED: Missing SMTP credentials in .env")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = f"SecureTransfer <{SMTP_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        # Connect to Gmail Server securely
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
            
        print(f"📧 EMAIL SENT to {to_email}")

    except Exception as e:
        # If email fails, we print the error but DO NOT crash the server.
        print(f"⚠️ EMAIL FAILED (Could not send to {to_email}): {e}")
# 🔐 AUTH ROUTES
# ==========================================

@app.post("/auth/register")
async def register(email: str = Form(...), password: str = Form(...)):
    if not r: raise HTTPException(500, "DB Offline")
    if r.exists(f"user:{email}"): raise HTTPException(400, "Email exists")
    
    user_data = {
        "email": email,
        "password_hash": hash_password(password),
        "status": "PENDING",
        "created_at": time.time(),
        "limit": 50 
    }
    r.hset(f"user:{email}", mapping=user_data)
    return {"message": "Registered. Wait for approval."}

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    # 1. SUPER ADMIN CHECK
    if email == ADMIN_EMAIL and password == ADMIN_PASS:
        token = str(uuid.uuid4())
        if r: 
            r.setex(f"session:{token}", 86400, ADMIN_EMAIL)
        return {"message": "Admin", "token": token, "email": email, "role": "ADMIN"}

    if not r: raise HTTPException(500, "DB Offline")
    
    # 2. NORMAL USER CHECK
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(401, "Invalid credentials")
    
    user_data = r.hgetall(user_key)
    
    if user_data["password_hash"] != hash_password(password):
        raise HTTPException(401, "Invalid credentials")
    
    # STATUS CHECKS
    if user_data["status"] == "PENDING": raise HTTPException(403, "Account pending approval")
    if user_data["status"] == "BANNED": raise HTTPException(403, "Account BANNED")

    token = str(uuid.uuid4())
    r.setex(f"session:{token}", 86400, email)
    
    return {"message": "Login successful", "token": token, "email": email, "role": "USER"}

# Change 'Form' to 'Body' and add 'embed=True'
@app.post("/auth/logout")
async def logout(request: Request):
    # This reads JSON or Form data manually to avoid 422 errors
    try:
        body = await request.json()
        token = body.get("session_token")
    except:
        form = await request.form()
        token = form.get("session_token")
        
    if token and r: 
        r.delete(f"session:{token}")
        
    return {"message": "Logged out"}
# ==========================================
# 🛡️ ADMIN ROUTES (UPDATED WITH ANALYTICS)
# ==========================================

@app.get("/admin/dashboard")
async def admin_dashboard(key: str):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    if not r: raise HTTPException(500, "DB Offline")

    files = []
    user_usage = {}  # Tracks how many bytes each user used
    type_counts = {} # Tracks file extensions (pdf, jpg, etc.)

    # 1. Process Files & Calculate Usage
    for k in r.keys("*"):
        if len(k) > 30 and "user:" not in k and "session:" not in k and "limit:" not in k:
            d = r.hgetall(k)
            
            # --- ANALYTICS LOGIC ---
            f_size = int(d.get("size", 0))
            sender = d.get("sender", "Unknown")
            fname = d.get("filename", "unknown")
            
            # Sum usage per user
            user_usage[sender] = user_usage.get(sender, 0) + f_size
            
            # Count file types
            ext = fname.split('.')[-1].lower() if '.' in fname else 'other'
            type_counts[ext] = type_counts.get(ext, 0) + 1
            # -----------------------

            files.append({
                "id": k, 
                "filename": fname, 
                "sender": sender,
                "size_mb": round(f_size / (1024 * 1024), 2), # Send size to UI
                "downloads": f"{d.get('downloads_count')}/{d.get('max_downloads')}",
                "protected": "Yes" if "password_hash" in d else "No"
            })

    # 2. Process Users & Add Storage Info
    users = []
    for k in r.scan_iter("user:*"):
        if isinstance(k, bytes): k = k.decode()
        u = r.hgetall(k)
        if u and "email" in u:
            email = u["email"]
            # Get bytes used from our calculation above, convert to MB
            used_mb = round(user_usage.get(email, 0) / (1024 * 1024), 2)
            
            users.append({
                "email": email,
                "status": u.get("status", "PENDING"),
                "limit": u.get("limit", 50),
                "storage_used_mb": used_mb # NEW FIELD
            })

    # 3. Global Server Disk Stats
    total, used, free = shutil.disk_usage(UPLOAD_DIR)
    disk_info = {
        "total_gb": round(total / (1024**3), 2),
        "used_gb": round(used / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "percent_full": round((used / total) * 100, 1)
    }

    return {
        "status": "Online",
        "total_active_files": len(files),
        "disk_info": disk_info,   # NEW: Server Health
        "file_types": type_counts, # NEW: Pie Chart Data
        "files": files, 
        "users": users
    }
@app.post("/admin/user_action")
async def user_action(
    background_tasks: BackgroundTasks,  # <--- This is the new part!
    key: str = Body(...), 
    email: str = Body(...), 
    action: str = Body(...)
):
    # 1. Check Admin Permission
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    
    # 2. Check if User Exists in DB
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(404, "User not found")

    # --- ACTION: APPROVE ---
    if action == "APPROVE":
        r.hset(user_key, "status", "ACTIVE")
        
        # Email Message
        subject = "✅ Account Approved - Axelites SecureTransfer"
        body = (
            f"Hello,\n\n"
            f"Good news! Your account ({email}) has been APPROVED by the Administrator.\n\n"
            f"You can now log in and start sending secure files."
        )
        # Send Email in Background (User doesn't wait)
        background_tasks.add_task(send_email_notification, email, subject, body)

    # --- ACTION: BAN ---
    elif action == "BAN":
        r.hset(user_key, "status", "BANNED")
        
        # Email Message
        subject = "🚫 Account Suspended - Axelites SecureTransfer"
        body = (
            f"Hello,\n\n"
            f"Your account ({email}) has been SUSPENDED due to a security violation.\n\n"
            f"If you believe this is an error, please contact the IT Administrator."
        )
        # Send Email in Background
        background_tasks.add_task(send_email_notification, email, subject, body)
    
    return {"message": f"User {action}ED (Email notification queued)"}
@app.post("/admin/user_limit")
async def user_limit(key: str = Body(...), email: str = Body(...), limit: int = Body(...)):
    if not verify_admin(key): raise HTTPException(403)
    r.hset(f"user:{email}", "limit", limit)
    return {"message": "Limit updated"}

@app.delete("/admin/delete_user/{email}")
async def delete_user(
    email: str, 
    key: str,
    background_tasks: BackgroundTasks # <--- New Parameter
):
    if not verify_admin(key): raise HTTPException(403)
    
    if r and r.exists(f"user:{email}"):
        r.delete(f"user:{email}")
        
        # Email Message
        subject = "⚠️ Account Deleted - Axelites SecureTransfer"
        body = f"Hello,\n\nYour account ({email}) has been permanently DELETED by the Administrator."
        
        # Send Email
        background_tasks.add_task(send_email_notification, email, subject, body)
        
        return {"status": "User Deleted & Notified"}
        
    return {"status": "User not found"}

@app.delete("/admin/delete/{file_id}")
async def delete_file(file_id: str, key: str):
    if not verify_admin(key): raise HTTPException(403)
    if r: r.delete(file_id)
    path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
    if os.path.exists(path): os.remove(path)
    return {"status": "Deleted"}

# ==========================================
# 📂 FILE ROUTES
# ==========================================

@app.get("/check/{file_id}")
async def check_file_info(file_id: str):
    if not r: raise HTTPException(500)
    data = r.hgetall(file_id)
    if not data: raise HTTPException(404)
    return {"found": True, "protected": "password_hash" in data, "filename": data["filename"]}

@app.post("/upload")
@limiter.limit("10/minute") 
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    expiration: int = Form(86400),
    password: str = Form(None),
    session_token: str = Form(...) 
):
    if not r: raise HTTPException(500, "DB Offline")
    
    # 1. Auth Check
    sender_email = get_current_user_email(session_token)
    if not sender_email: raise HTTPException(401, "Unauthorized")

    # 2. Ban & Limit Check
    if sender_email != ADMIN_EMAIL:
        user_data = r.hgetall(f"user:{sender_email}")
        if not user_data: raise HTTPException(401)
        if user_data.get("status") == "BANNED":
            raise HTTPException(403, "🚫 Account BANNED.")

        # Daily Limit
        today = datetime.now().strftime("%Y-%m-%d")
        limit_key = f"limit:{sender_email}:{today}"
        curr = int(r.get(limit_key) or 0)
        limit = int(user_data.get("limit", 50))
        
        if curr >= limit: raise HTTPException(429, "Daily Limit Reached")
        r.incr(limit_key)
        r.expire(limit_key, 86400)

    try:
        # 1. Read the file
        file_content = await file.read()
        file_size = len(file_content) 

        # 2. Virus Scan
        scan_file_for_virus(file_content)

        # 3. AI Brain Scan (Only for files < 1MB to keep it fast)
        if file_size < 1024 * 1024:
            # 👇 FIXED: Changed 'content' to 'file_content'
            scan_with_ollama(file_content, file.filename) 

        # 4. Encryption (Fernet)
        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted_content = cipher.encrypt(file_content)

        # 5. Save to Disk
        file_id = str(uuid.uuid4())
        with open(os.path.join(UPLOAD_DIR, f"{file_id}.enc"), "wb") as f:
            f.write(encrypted_content)

        # 6. Save Metadata to Redis
        metadata = {
            "filename": file.filename,
            "key": key.decode(),
            "max_downloads": 100,
            "downloads_count": 0,
            "sender": sender_email,
            "size": file_size 
        }
        if password and password.strip():
            metadata["password_hash"] = hash_password(password.strip())

        r.hset(file_id, mapping=metadata)
        r.expire(file_id, expiration)

        return {"id": file_id, "filename": file.filename, "message": "Success"}

    # Catch Security Blocks explicitly to show the right error message
    except HTTPException as he:
        raise he 
    except Exception as e: 
        raise HTTPException(500, f"Server Error: {str(e)}")

@app.post("/download/{file_id}")
@limiter.limit("20/minute") 
async def download_file(request: Request, file_id: str, password: str = Body(None, embed=True)):
    if not r: raise HTTPException(500)
    data = r.hgetall(file_id)
    if not data: raise HTTPException(404)

    if "password_hash" in data:
        if not password or hash_password(password) != data["password_hash"]:
            raise HTTPException(403, "Wrong password")

    if int(data.get("downloads_count", 0)) >= int(data.get("max_downloads", 100)):
        r.delete(file_id)
        os.remove(os.path.join(UPLOAD_DIR, f"{file_id}.enc"))
        raise HTTPException(410, "Expired")

    r.hincrby(file_id, "downloads_count", 1)
    
    with open(os.path.join(UPLOAD_DIR, f"{file_id}.enc"), "rb") as f:
        encrypted = f.read()
    
    cipher = Fernet(data['key'].encode())
    return Response(cipher.decrypt(encrypted), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{data["filename"]}"'})

# --- CLEANUP ---
def cleanup():
    while True:
        time.sleep(300)
        try:
            if r:
                for f in os.listdir(UPLOAD_DIR):
                    if f.endswith(".enc") and not r.exists(f.replace(".enc", "")):
                        os.remove(os.path.join(UPLOAD_DIR, f))
        except: pass

@app.on_event("startup")
def start_tasks():
    threading.Thread(target=cleanup, daemon=True).start()