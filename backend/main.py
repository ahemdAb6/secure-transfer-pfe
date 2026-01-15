import shutil
import os
import uuid
import re
import requests
import json
import io
import threading
import time
import hashlib
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote 

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Body, BackgroundTasks
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet
from pypdf import PdfReader 


try:
    from dotenv import load_dotenv
    load_dotenv() 
except ImportError:
    print("⚠️ WARNING: 'python-dotenv' library missing. Using system defaults.")

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


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@axelites.com") 
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "admin123")
REDIS_HOST = os.getenv("REDIS_HOST", "redis") 

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = os.getenv("SMTP_EMAIL")       
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") 

r = None
if redis:
    try:
        r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis Connected")
    except:
        print("⚠️ Redis Connection Failed")

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost", "http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

#fonctions

def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_current_user_email(session_token: str):
    if not session_token or not r: return None
    return r.get(f"session:{session_token}")

def verify_admin(key: str) -> bool:
    if key == ADMIN_SECRET: return True
    if r:
        session_email = r.get(f"session:{key}")
        if session_email == ADMIN_EMAIL:
            return True
    return False

def scan_file_for_virus(content: bytes):
    if not clamd: return
    try:
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        if cd.ping() != 'PONG': return 
        scan_result = cd.instream(io.BytesIO(content))
        if scan_result and scan_result['stream'][0] == 'FOUND':
            raise HTTPException(status_code=400, detail=f"VIRUS DETECTED: {scan_result['stream'][1]}")
    except HTTPException as he: raise he
    except Exception: pass

def send_email_notification(to_email: str, subject: str, message: str):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("⚠️ EMAIL SKIPPED: Missing SMTP credentials in .env")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = f"SecureTransfer <{SMTP_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"📧 EMAIL SENT to {to_email}")
    except Exception as e:
        print(f"⚠️ EMAIL FAILED (Could not send to {to_email}): {e}")

OLLAMA_URL = "http://ollama:11434/api/generate"
AI_MODEL = "gemma:2b"


def scan_with_ollama(content: bytes, filename: str):
    text_preview = ""
    try:
    
        if filename.endswith(".pdf"):
            pdf_file = io.BytesIO(content)
            reader = PdfReader(pdf_file)
            if len(reader.pages) > 0: text_preview += reader.pages[0].extract_text()
        else:
            text_preview = content.decode('utf-8')
            
        if not text_preview.strip(): return "SAFE" 

    except Exception:
        return "SAFE" 

    
    patterns = {
        "AWS Key": r'AKIA[0-9A-Z]{16}',
        "Private Key": r'BEGIN RSA PRIVATE KEY',
        "Hardcoded Password": r'(?:password|secret)\s*=\s*[\'"][^\'"]+[\'"]'
    }

    for threat, regex in patterns.items():
        if re.search(regex, text_preview):
            print(f"🚫 SENTINEL BLOCKED: {threat} detected via Regex")
            raise HTTPException(status_code=400, detail=f"⚠️ SECURITY ALERT: {threat} Detected.")

    if len(text_preview) > 1500:
        text_preview = text_preview[:1500]

    prompt = f"""
    You are a Data Loss Prevention (DLP) Sentinel. Your job is to classify text as SAFE or BLOCK.

    --- EXAMPLES OF BLOCK ---
    Text: "Here is the database dump with user passwords." -> BLOCK
    Text: "The project code name is Project X, do not share." -> BLOCK
    Text: "Customer list: John Doe, 555-0199, john@email.com" -> BLOCK
    
    --- EXAMPLES OF SAFE ---
    Text: "import os; print('hello world')" -> SAFE
    Text: "The meeting is at 5pm." -> SAFE
    Text: "I need to fix the css bug on the navbar." -> SAFE

    --- ANALYZE THIS ---
    Text: "{text_preview}"

    INSTRUCTIONS:
    - If the text leaks company secrets, customer data, or credentials: Reply BLOCK.
    - If it is code, homework, or general chat: Reply SAFE.
    - Reply with ONE WORD ONLY.
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": AI_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1 
            }
        }, timeout=20)
        
        if response.status_code == 200:
            result = response.json().get("response", "").strip().upper()
            import string
            result_clean = result.translate(str.maketrans('', '', string.punctuation))

            print(f"🔍 SENTINEL ANALYSIS: {filename}")
            print(f"🤖 GEMMA THOUGHT: '{result_clean}'")

            if "BLOCK" in result_clean:
                msg = "⚠️ AI SECURITY ALERT: Contextual Data Leak Detected."
                raise HTTPException(status_code=400, detail=msg)
                 
            return "SAFE"

    except requests.exceptions.RequestException:
        print("⚠️ AI Service busy. Allowing file.")
        return "SAFE"
#auth routes

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
    if email == ADMIN_EMAIL and password == ADMIN_PASS:
        token = str(uuid.uuid4())
        if r: r.setex(f"session:{token}", 86400, ADMIN_EMAIL)
        return {"message": "Admin", "token": token, "email": email, "role": "ADMIN"}

    if not r: raise HTTPException(500, "DB Offline")
    
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(401, "Invalid credentials")
    
    user_data = r.hgetall(user_key)
    if user_data["password_hash"] != hash_password(password):
        raise HTTPException(401, "Invalid credentials")
    
    if user_data["status"] == "PENDING": raise HTTPException(403, "Account pending approval")
    if user_data["status"] == "BANNED": raise HTTPException(403, "Account BANNED")

    token = str(uuid.uuid4())
    r.setex(f"session:{token}", 86400, email)
    return {"message": "Login successful", "token": token, "email": email, "role": "USER"}

@app.post("/auth/logout")
async def logout(request: Request):
    try:
        body = await request.json()
        token = body.get("session_token")
    except:
        form = await request.form()
        token = form.get("session_token")
        
    if token and r: 
        r.delete(f"session:{token}")
    return {"message": "Logged out"}

# admin routes

@app.get("/admin/dashboard")
async def admin_dashboard(key: str):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    if not r: raise HTTPException(500, "DB Offline")

    files = []
    user_usage = {} 
    type_counts = {}

    for k in r.keys("*"):
        if len(k) > 30 and "user:" not in k and "session:" not in k and "limit:" not in k:
            d = r.hgetall(k)
            f_size = int(d.get("size", 0))
            sender = d.get("sender", "Unknown")
            fname = d.get("filename", "unknown")
            user_usage[sender] = user_usage.get(sender, 0) + f_size
            ext = fname.split('.')[-1].lower() if '.' in fname else 'other'
            type_counts[ext] = type_counts.get(ext, 0) + 1

            files.append({
                "id": k, 
                "filename": fname, 
                "sender": sender,
                "size_mb": round(f_size / (1024 * 1024), 2),
                "downloads": f"{d.get('downloads_count')}/{d.get('max_downloads')}",
                "protected": "Yes" if "password_hash" in d else "No"
            })

    users = []
    for k in r.scan_iter("user:*"):
        if isinstance(k, bytes): k = k.decode()
        u = r.hgetall(k)
        if u and "email" in u:
            email = u["email"]
            used_mb = round(user_usage.get(email, 0) / (1024 * 1024), 2)
            users.append({
                "email": email,
                "status": u.get("status", "PENDING"),
                "limit": u.get("limit", 50),
                "storage_used_mb": used_mb
            })

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
        "disk_info": disk_info,
        "file_types": type_counts,
        "files": files, 
        "users": users
    }

@app.post("/admin/user_action")
async def user_action(
    background_tasks: BackgroundTasks,
    key: str = Body(...), 
    email: str = Body(...), 
    action: str = Body(...)
):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(404, "User not found")

    if action == "APPROVE":
        r.hset(user_key, "status", "ACTIVE")
        background_tasks.add_task(send_email_notification, email, "✅ Account Approved", "Your account has been approved.")
    elif action == "BAN":
        r.hset(user_key, "status", "BANNED")
        background_tasks.add_task(send_email_notification, email, "🚫 Account Suspended", "Your account has been suspended.")
    
    return {"message": f"User {action}ED"}

@app.post("/admin/user_limit")
async def user_limit(key: str = Body(...), email: str = Body(...), limit: int = Body(...)):
    if not verify_admin(key): raise HTTPException(403)
    r.hset(f"user:{email}", "limit", limit)
    return {"message": "Limit updated"}

@app.delete("/admin/delete_user/{email}")
async def delete_user(email: str, key: str, background_tasks: BackgroundTasks):
    if not verify_admin(key): raise HTTPException(403)
    if r and r.exists(f"user:{email}"):
        r.delete(f"user:{email}")
        background_tasks.add_task(send_email_notification, email, "⚠️ Account Deleted", "Your account has been deleted.")
        return {"status": "User Deleted"}
    return {"status": "User not found"}

@app.delete("/admin/delete/{file_id}")
async def delete_file(file_id: str, key: str):
    if not verify_admin(key): raise HTTPException(403)
    if r: r.delete(file_id)
    path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
    if os.path.exists(path): os.remove(path)
    return {"status": "Deleted"}

# files routes

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
    
    sender_email = get_current_user_email(session_token)
    if not sender_email: raise HTTPException(401, "Unauthorized")

    if sender_email != ADMIN_EMAIL:
        user_data = r.hgetall(f"user:{sender_email}")
        if not user_data: raise HTTPException(401)
        if user_data.get("status") == "BANNED": raise HTTPException(403, "🚫 Account BANNED.")

        today = datetime.now().strftime("%Y-%m-%d")
        limit_key = f"limit:{sender_email}:{today}"
        curr = int(r.get(limit_key) or 0)
        limit = int(user_data.get("limit", 50))
        if curr >= limit: raise HTTPException(429, "Daily Limit Reached")
        r.incr(limit_key)
        r.expire(limit_key, 86400)

    try:
        file_content = await file.read()
        file_size = len(file_content) 

        scan_file_for_virus(file_content)

        
        if file_size < 1024 * 1024:
            scan_with_ollama(file_content, file.filename) 

        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted_content = cipher.encrypt(file_content)

        file_id = str(uuid.uuid4())
        with open(os.path.join(UPLOAD_DIR, f"{file_id}.enc"), "wb") as f:
            f.write(encrypted_content)

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

    except HTTPException as he: raise he 
    except Exception as e: raise HTTPException(500, f"Server Error: {str(e)}")

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
        path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
        if os.path.exists(path): os.remove(path)
        raise HTTPException(410, "Expired")

    r.hincrby(file_id, "downloads_count", 1)
    
    with open(os.path.join(UPLOAD_DIR, f"{file_id}.enc"), "rb") as f:
        encrypted = f.read()
    
    cipher = Fernet(data['key'].encode())
    decrypted_content = cipher.decrypt(encrypted)
    
    
    filename_encoded = quote(data["filename"])

    return Response(
        decrypted_content, 
        media_type="application/octet-stream", 
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{filename_encoded}"
        }
    )


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