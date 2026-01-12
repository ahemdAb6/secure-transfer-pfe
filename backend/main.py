import shutil
import os
import uuid
import io
import threading
import time
import hashlib
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Body
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet

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

# ADMIN CREDENTIALS
ADMIN_EMAIL = "admin@axelites.com"
ADMIN_PASS = "admin123"
ADMIN_SECRET = "admin123" # Master Key

# Connexion Redis
r = None
if redis:
    try:
        r = redis.Redis(host='redis', port=6379, decode_responses=True)
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        if cd.ping() != 'PONG': return 
        scan_result = cd.instream(io.BytesIO(content))
        if scan_result and scan_result['stream'][0] == 'FOUND':
            raise HTTPException(status_code=400, detail=f"VIRUS DETECTED: {scan_result['stream'][1]}")
    except HTTPException as he: raise he
    except Exception: pass

# ==========================================
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
            # Store simply the email. verify_admin will check if this email is ADMIN_EMAIL
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

@app.post("/auth/logout")
async def logout(session_token: str = Form(...)):
    if r: r.delete(f"session:{session_token}")
    return {"message": "Logged out"}

# ==========================================
# 🛡️ ADMIN ROUTES
# ==========================================

@app.get("/admin/dashboard")
async def admin_dashboard(key: str):
    if not verify_admin(key): raise HTTPException(403, "Access Denied")
    if not r: raise HTTPException(500, "DB Offline")

    # 1. Files
    files = []
    for k in r.keys("*"):
        if len(k) > 30 and "user:" not in k and "session:" not in k and "limit:" not in k:
            d = r.hgetall(k)
            files.append({
                "id": k, 
                "filename": d.get("filename"), 
                "sender": d.get("sender"),
                "downloads": f"{d.get('downloads_count')}/{d.get('max_downloads')}",
                "protected": "Yes" if "password_hash" in d else "No"
            })

    # 2. Users (Fixed Loop for Robustness)
    users = []
    for k in r.scan_iter("user:*"):
        if isinstance(k, bytes): k = k.decode()
        u = r.hgetall(k)
        if u and "email" in u:
            users.append({
                "email": u["email"],
                "status": u.get("status", "PENDING"),
                "limit": u.get("limit", 50)
            })

    return {"total_active_files": len(files), "status": "Online", "files": files, "users": users}

@app.post("/admin/user_action")
async def user_action(key: str = Body(...), email: str = Body(...), action: str = Body(...)):
    if not verify_admin(key): raise HTTPException(403)
    
    user_key = f"user:{email}"
    if not r.exists(user_key): raise HTTPException(404, "User not found")

    if action == "APPROVE": r.hset(user_key, "status", "ACTIVE")
    elif action == "BAN": r.hset(user_key, "status", "BANNED")
    
    return {"message": f"User {action}ED"}

@app.post("/admin/user_limit")
async def user_limit(key: str = Body(...), email: str = Body(...), limit: int = Body(...)):
    if not verify_admin(key): raise HTTPException(403)
    r.hset(f"user:{email}", "limit", limit)
    return {"message": "Limit updated"}

@app.delete("/admin/delete_user/{email}")
async def delete_user(email: str, key: str):
    if not verify_admin(key): raise HTTPException(403)
    if r: r.delete(f"user:{email}")
    return {"status": "User Deleted"}

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
        file_content = await file.read()
        scan_file_for_virus(file_content)

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
            "sender": sender_email 
        }
        if password and password.strip():
            metadata["password_hash"] = hash_password(password.strip())

        r.hset(file_id, mapping=metadata)
        r.expire(file_id, expiration)

        return {"id": file_id, "filename": file.filename, "message": "Success"}

    except Exception as e: raise HTTPException(500, str(e))

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