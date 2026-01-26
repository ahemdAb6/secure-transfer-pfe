import shutil
import os
import uuid
import bcrypt
import re
import io
import threading
import time
import smtplib
import base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Body, BackgroundTasks, Depends
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader 
from pydantic import BaseModel
import logging
from logging.handlers import RotatingFileHandler 

# --- CRYPTO IMPORTS ---
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import torch.nn.functional as F

# --- LOGGING SETUP ---
log_handler = RotatingFileHandler(
    "securetransfer.log", 
    maxBytes=5 * 1024 * 1024, 
    backupCount=3,            
    encoding='utf-8'
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

logger.info("🚀 SecureTransfer API starting...")

# --- ENV & CONFIG ---
try:
    from dotenv import load_dotenv
    load_dotenv() 
except ImportError: pass

try:
    import redis
except ImportError:
    redis = None
    logger.warning("⚠️ Redis lib missing")

try:
    import clamd
except ImportError:
    clamd = None
    logger.warning("⚠️ ClamAV lib missing")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL") 
ADMIN_PASS = os.getenv("ADMIN_PASS")
ADMIN_SECRET = os.getenv("ADMIN_SECRET")
REDIS_HOST = os.getenv("REDIS_HOST") 
SMTP_EMAIL = os.getenv("SMTP_EMAIL")       
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") 
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# --- REDIS CONNECTION ---
r = None
if redis:
    try:
        r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
        r.ping()
        logger.info("✅ Redis Connected")
    except Exception as e:
        logger.error(f"⚠️ Redis Connection Failed: {str(e)}")

# --- AI MODEL LOADING ---
MODEL_PATH = "/app/my_model"
ai_tokenizer = None
ai_model = None

try:
    logger.info("⏳ Loading AI Model...")
    ai_tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    ai_model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    logger.info("✅ AI Model Loaded Successfully")
except Exception:
    try:
        logger.info("⚠️ Docker path failed, trying local path...")
        ai_tokenizer = AutoTokenizer.from_pretrained("./my_model")
        ai_model = AutoModelForSequenceClassification.from_pretrained("./my_model")
        logger.info("✅ AI Model Loaded Successfully (Local)")
    except Exception:
        logger.warning("❌ Failed to load AI model. AI features disabled.")

# --- FASTAPI SETUP ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"]
)

# --- MODELS ---
class InitUploadModel(BaseModel):
    filename: str
    total_size: int
    session_token: str

class FinalizeUploadModel(BaseModel):
    upload_id: str
    session_token: str
    expiration: int = 86400
    password: Optional[str] = None
    recipient_email: Optional[str] = None

# --- CRYPTO HELPERS (STREAMING) ---
def encrypt_file_stream(source_path, dest_path, key):
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    with open(source_path, "rb") as f_in, open(dest_path, "wb") as f_out:
        f_out.write(iv)
        while True:
            chunk = f_in.read(64 * 1024)
            if not chunk: break
            f_out.write(encryptor.update(chunk))
        f_out.write(encryptor.finalize())

def iter_file_decrypt(file_path, key):
    with open(file_path, "rb") as f:
        iv = f.read(16)
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        while True:
            chunk = f.read(64 * 1024)
            if not chunk: break
            yield decryptor.update(chunk)
        yield decryptor.finalize()

# --- HELPER FUNCTIONS ---
def hash_password(pwd: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd.encode('utf-8'), salt).decode('utf-8')

def verify_password(pwd: str, hashed_pwd: str) -> bool:
    return bcrypt.checkpw(pwd.encode('utf-8'), hashed_pwd.encode('utf-8'))

def get_current_user_email(session_token: str):
    if not session_token or not r: return None
    return r.get(f"session:{session_token}")

def verify_admin(key: str) -> bool:
    if key == ADMIN_SECRET: return True
    if r:
        session_email = r.get(f"session:{key}")
        if session_email == ADMIN_EMAIL: return True
    return False

def scan_file_for_virus(content: bytes):
    if not clamd: return
    try:
        logger.info("🦠 Starting Virus Scan...")
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        if cd.ping() != 'PONG': return
        scan_result = cd.instream(io.BytesIO(content))
        if scan_result and scan_result['stream'][0] == 'FOUND':
            virus_name = scan_result['stream'][1]
            logger.critical(f"🚨 VIRUS DETECTED: {virus_name}")
            raise HTTPException(status_code=400, detail=f"VIRUS DETECTED: {virus_name}")
        logger.info("✅ Virus Scan Clean")
    except HTTPException as he: raise he
    except Exception: pass

def scan_file_content(content: bytes, filename: str):
    logger.info(f"🤖 Starting AI DLP Scan for {filename}...")
    text_preview = ""
    MAX_PAGES = 5    
    try:
        if filename.lower().endswith(".pdf"):
            try:
                pdf_file = io.BytesIO(content)
                reader = PdfReader(pdf_file)
                pages_to_scan = min(len(reader.pages), MAX_PAGES) 
                for i in range(pages_to_scan):
                    page_text = reader.pages[i].extract_text()
                    if page_text: text_preview += page_text + "\n"
            except: pass
        else:
            try: text_preview = content[:10000].decode('utf-8', errors='ignore')
            except: return "SAFE"
            
        if not text_preview.strip(): return "SAFE"

        patterns = {
            "AWS Key": r'AKIA[0-9A-Z]{16}',
            "Private Key": r'BEGIN RSA PRIVATE KEY',
            "Hardcoded Password": r'(?:password|secret)\s*=\s*[\'"][^\'"]+[\'"]'
        }
        for threat, regex in patterns.items():
            if re.search(regex, text_preview):
                logger.warning(f"🚫 BLOCKED: {threat} detected in {filename}")
                raise HTTPException(status_code=400, detail=f"⚠️ SECURITY ALERT: {threat} Detected.")

        if ai_tokenizer and ai_model:
            inputs = ai_tokenizer(text_preview, return_tensors="pt", truncation=True, max_length=512, padding=True)
            with torch.no_grad(): outputs = ai_model(**inputs)
            probabilities = F.softmax(outputs.logits, dim=-1)
            danger_score = probabilities[0][1].item() * 100
            
            logger.info(f"🧠 AI Score: {danger_score:.2f}% risk")
            if danger_score > 50:
                logger.warning(f"🚫 AI BLOCKED {filename}")
                raise HTTPException(status_code=400, detail="⚠️ AI SECURITY ALERT: Sensitive Data Detected.")
    except HTTPException as he: raise he
    except Exception: pass

def send_email_notification(to_email: str, subject: str, message: str):
    if not SMTP_EMAIL: return
    try:
        msg = MIMEMultipart()
        msg['From'] = f"SecureTransfer <{SMTP_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"📧 Admin Email sent to {to_email}")
    except Exception: pass

def send_file_notification(to_email: str, filename: str, link: str, sender: str):
    if not SMTP_EMAIL: return
    try:
        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="padding: 20px; border: 1px solid #ddd; border-radius: 10px; max-width: 500px;">
              <h2 style="color: #6366f1;">SecureTransfer</h2>
              <p><strong>{sender}</strong> has sent you a file.</p>
              <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0;">📄 <strong>File:</strong> {filename}</p>
              </div>
              <a href="{link}" style="background-color: #6366f1; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Download File</a>
            </div>
          </body>
        </html>
        """
        msg = MIMEMultipart()
        msg['From'] = f"SecureTransfer <{SMTP_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = f"📂 {sender} sent you a file"
        msg.attach(MIMEText(html_content, 'html'))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"📧 File Link sent to {to_email}")
    except Exception: pass

# --- AUTH ROUTES ---
@app.post("/auth/register")
async def register(email: str = Form(...), password: str = Form(...)):
    if not r: raise HTTPException(500, "DB Offline")
    if r.exists(f"user:{email}"): raise HTTPException(400, "Email exists")
    user_data = {"email": email, "password_hash": hash_password(password), "status": "PENDING", "created_at": time.time(), "limit": 50}
    r.hset(f"user:{email}", mapping=user_data)
    logger.info(f"👤 New User Registered: {email}")
    return {"message": "Registered. Wait for approval."}

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    if email == ADMIN_EMAIL and password == ADMIN_PASS:
        token = str(uuid.uuid4())
        if r: r.setex(f"session:{token}", 86400, ADMIN_EMAIL)
        logger.info(f"🛡️ Admin Logged In: {email}")
        return {"message": "Admin", "token": token, "email": email, "role": "ADMIN"}
    if not r: raise HTTPException(500, "DB Offline")
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(401, "Invalid credentials")
    user_data = r.hgetall(user_key)
    if not verify_password(password, user_data["password_hash"]): raise HTTPException(401, "Invalid credentials")
    if user_data["status"] == "PENDING": raise HTTPException(403, "Account pending approval")
    if user_data["status"] == "BANNED": raise HTTPException(403, "Account BANNED")
    token = str(uuid.uuid4())
    r.setex(f"session:{token}", 86400, email)
    logger.info(f"👤 User Logged In: {email}")
    return {"message": "Login successful", "token": token, "email": email, "role": "USER"}

@app.post("/auth/logout")
async def logout(request: Request):
    try: body = await request.json(); token = body.get("session_token")
    except: form = await request.form(); token = form.get("session_token") 
    if token and r: 
        email = r.get(f"session:{token}")
        r.delete(f"session:{token}")
        logger.info(f"👋 User Logged Out: {email}")
    return {"message": "Logged out"}

# --- ADMIN ROUTES ---
@app.get("/admin/dashboard")
async def admin_dashboard(key: str):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    if not r: raise HTTPException(500, "DB Offline")
    files, user_usage, type_counts = [], {}, {}
    for k in r.keys("*"):
        if len(k) > 30 and "user:" not in k and "session:" not in k and "limit:" not in k and "upload_meta" not in k:
            d = r.hgetall(k)
            f_size = int(d.get("size", 0))
            sender = d.get("sender", "Unknown")
            fname = d.get("filename", "unknown")
            user_usage[sender] = user_usage.get(sender, 0) + f_size
            ext = fname.split('.')[-1].lower() if '.' in fname else 'other'
            type_counts[ext] = type_counts.get(ext, 0) + 1
            files.append({"id": k, "filename": fname, "sender": sender, "size_mb": round(f_size/(1024*1024), 2), "downloads": f"{d.get('downloads_count')}/{d.get('max_downloads')}", "protected": "Yes" if "password_hash" in d else "No"})
    users = []
    for k in r.scan_iter("user:*"):
        if isinstance(k, bytes): k = k.decode()
        u = r.hgetall(k)
        if u and "email" in u:
            users.append({"email": u["email"], "status": u.get("status", "PENDING"), "limit": u.get("limit", 50), "storage_used_mb": round(user_usage.get(u["email"], 0)/(1024*1024), 2)})
    total, used, free = shutil.disk_usage(UPLOAD_DIR)
    return {"status": "Online", "disk_info": {"total_gb": round(total/(1024**3), 2), "used_gb": round(used/(1024**3), 2), "percent_full": round((used/total)*100, 1)}, "file_types": type_counts, "files": files, "users": users}

@app.post("/admin/user_action")
async def user_action(background_tasks: BackgroundTasks, key: str = Body(...), email: str = Body(...), action: str = Body(...)):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    if action == "APPROVE": r.hset(f"user:{email}", "status", "ACTIVE")
    elif action == "BAN": r.hset(f"user:{email}", "status", "BANNED")
    logger.info(f"👮 Admin Action: {action} on {email}")
    return {"message": f"User {action}ED"}

@app.delete("/admin/delete_user/{email}")
async def delete_user(email: str, key: str):
    if not verify_admin(key): raise HTTPException(403)
    r.delete(f"user:{email}")
    logger.warning(f"🗑️ User Deleted: {email}")
    return {"status": "User Deleted"}

@app.delete("/admin/delete/{file_id}")
async def delete_file_admin(file_id: str, key: str):
    if not verify_admin(key): raise HTTPException(403)
    r.delete(file_id)
    path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
    if os.path.exists(path): os.remove(path)
    logger.warning(f"🗑️ Admin Deleted File: {file_id}")
    return {"status": "Deleted"}

@app.post("/admin/user_limit")
async def user_limit(key: str = Body(...), email: str = Body(...), limit: int = Body(...)):
    if not verify_admin(key): raise HTTPException(403)
    r.hset(f"user:{email}", "limit", limit)
    return {"message": "Limit updated"}

# --- CHUNKING UPLOAD ROUTES (OPTIMIZED RAM) ---

@app.post("/upload/init")
async def init_upload(data: InitUploadModel):
    sender_email = get_current_user_email(data.session_token)
    if not sender_email: raise HTTPException(401, "Unauthorized")
    upload_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"temp_{upload_id}")
    with open(temp_path, "wb") as f: pass 
    r.hset(f"upload_meta:{upload_id}", mapping={"filename": data.filename, "sender": sender_email, "total_size": data.total_size})
    r.expire(f"upload_meta:{upload_id}", 3600) 
    logger.info(f"📤 Start Upload: {data.filename} ({data.total_size/1024/1024:.2f} MB) by {sender_email}")
    return {"upload_id": upload_id}

@app.post("/upload/chunk")
async def upload_chunk(upload_id: str = Form(...), file: UploadFile = File(...)):
    temp_path = os.path.join(UPLOAD_DIR, f"temp_{upload_id}")
    with open(temp_path, "ab") as f:
        f.write(await file.read())
    return {"status": "ok"}

@app.post("/upload/finalize")
async def finalize_upload(background_tasks: BackgroundTasks, request: Request, data: FinalizeUploadModel):
    meta_key = f"upload_meta:{data.upload_id}"
    if not r.exists(meta_key): raise HTTPException(404, "Upload not found")
    meta = r.hgetall(meta_key)
    sender_email = meta["sender"]
    filename = meta["filename"]
    temp_path = os.path.join(UPLOAD_DIR, f"temp_{data.upload_id}")

    if not os.path.exists(temp_path): raise HTTPException(404, "Temp file missing")

    logger.info(f"🛡️ Security Scan starting for: {filename}")
    try:
        # 1. SMART SECURITY
        with open(temp_path, "rb") as f:
            header_content = f.read(10 * 1024 * 1024) 
            scan_file_content(header_content, filename) 
            
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0)
            
            if file_size < 300 * 1024 * 1024: 
                content_for_virus = f.read()
                scan_file_for_virus(content_for_virus)
            else:
                logger.warning(f"⏩ Virus scan skipped (Large File): {filename}")

        # 2. ENCRYPTION
        logger.info(f"🔐 Encrypting {filename} (Streaming Mode)...")
        key = os.urandom(32) 
        final_id = str(uuid.uuid4())
        final_path = os.path.join(UPLOAD_DIR, f"{final_id}.enc")
        
        encrypt_file_stream(temp_path, final_path, key)
            
        os.remove(temp_path)
        r.delete(meta_key)

    except HTTPException as he:
        if os.path.exists(temp_path): os.remove(temp_path)
        logger.error(f"❌ Blocked: {he.detail}")
        raise he
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        logger.error(f"Finalize Error: {e}")
        raise HTTPException(500, f"Processing Failed: {str(e)}")

    key_b64 = base64.urlsafe_b64encode(key).decode()

    file_metadata = {
        "filename": filename,
        "key": key_b64,
        "max_downloads": 100,
        "downloads_count": 0,
        "sender": sender_email,
        "size": file_size 
    }
    if data.password:
        file_metadata["password_hash"] = hash_password(data.password)

    r.hset(final_id, mapping=file_metadata)
    r.expire(final_id, data.expiration)
    
    logger.info(f"✅ Upload Complete: {final_id}")

    if data.recipient_email:
        base_url = str(request.base_url).rstrip("/")
        link = f"{base_url}?id={final_id}"
        background_tasks.add_task(send_file_notification, data.recipient_email, filename, link, sender_email)

    return {"id": final_id, "filename": filename, "message": "Success"}

# --- DOWNLOAD ROUTES (STREAMING) ---

@app.get("/check/{file_id}")
async def check_file_info(file_id: str):
    if not r: raise HTTPException(500)
    data = r.hgetall(file_id)
    if not data: raise HTTPException(404)
    return {"found": True, "protected": "password_hash" in data, "filename": data["filename"]}

@app.post("/download/{file_id}")
async def download_file(file_id: str, password: str = Body(None, embed=True)):
    if not r: raise HTTPException(500)
    data = r.hgetall(file_id)
    if not data: raise HTTPException(404)

    if "password_hash" in data:
        if not password or not verify_password(password, data["password_hash"]):
            logger.warning(f"🔒 Failed download attempt (Bad Password): {file_id}")
            raise HTTPException(403, "Wrong password")

    r.hincrby(file_id, "downloads_count", 1)
    logger.info(f"⬇️ Download Started: {data['filename']}")
    
    try:
        path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
        if not os.path.exists(path): raise HTTPException(404, "File missing")

        key = base64.urlsafe_b64decode(data['key'])
        from urllib.parse import quote
        filename_encoded = quote(data["filename"])
        
        return StreamingResponse(
            iter_file_decrypt(path, key),
            media_type="application/octet-stream", 
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{filename_encoded}"}
        )
    except Exception as e:
        logger.error(f"Download Error: {str(e)}")
        raise HTTPException(500, "Download Error")

# --- CLEANUP TASK ---
def cleanup():
    while True:
        time.sleep(300) 
        try:
            if r:
                for f in os.listdir(UPLOAD_DIR):
                    if f.endswith(".enc"):
                        file_id = f.replace(".enc", "")
                        if not r.exists(file_id):
                            try: os.remove(os.path.join(UPLOAD_DIR, f))
                            except: pass
        except Exception: pass

@app.on_event("startup")
def start_tasks():
    threading.Thread(target=cleanup, daemon=True).start()