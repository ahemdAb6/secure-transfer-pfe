import shutil
import os
import uuid
import io
import threading
import time
import hashlib  # Standard library for passwords (No installation needed)
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Body
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet

# --- SAFE IMPORTS (Prevents crash if Docker libraries are missing) ---
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
    print("⚠️ WARNING: 'slowapi' missing. Rate limiting disabled.")
    # Dummy mocks to prevent crash
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

# Setup Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup CORS (Crucial for Frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPER FUNCTIONS ---

def scan_file_for_virus(content: bytes):
    """Scans file in RAM. Raises 400 if virus found."""
    if not clamd: return
    try:
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        if cd.ping() != 'PONG': return 

        scan_result = cd.instream(io.BytesIO(content))
        if scan_result and 'stream' in scan_result:
            status, virus_name = scan_result['stream']
            if status == 'FOUND':
                print(f"🚨 SECURITY ALERT: {virus_name}")
                raise HTTPException(status_code=400, detail=f"VIRUS DETECTED: {virus_name}")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"⚠️ Antivirus Warning: {e}")

def hash_password(pwd: str) -> str:
    """Securely hashes password using SHA256 (Standard, No Crash)"""
    return hashlib.sha256(pwd.encode()).hexdigest()

# --- ROUTES ---

@app.get("/")
def read_root():
    return {"status": "Secure Server Running"}

# NEW: Check if file exists and needs password
@app.get("/check/{file_id}")
async def check_file_info(file_id: str):
    if not r: raise HTTPException(status_code=500, detail="Database Offline")
    data = r.hgetall(file_id)
    if not data: raise HTTPException(status_code=404, detail="File not found")
    
    is_protected = "password_hash" in data
    return {"found": True, "protected": is_protected, "filename": data["filename"]}

@app.post("/upload")
@limiter.limit("10/minute") 
async def upload_file(
    request: Request,
    file: UploadFile = File(...), 
    expiration: int = Form(86400),
    password: str = Form(None)
):
    if not r: raise HTTPException(status_code=500, detail="Database Offline")

    try:
        # 1. Read
        file_content = await file.read()

        # 2. Virus Scan
        scan_file_for_virus(file_content)

        # 3. Encrypt
        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted_content = cipher.encrypt(file_content)

        # 4. Save to Disk
        file_id = str(uuid.uuid4())
        secure_filename = f"{file_id}.enc"
        file_location = os.path.join(UPLOAD_DIR, secure_filename)

        with open(file_location, "wb") as f:
            f.write(encrypted_content)

        # 5. Metadata (Max Downloads & Password)
        metadata = {
            "filename": file.filename,
            "key": key.decode(),
            "max_downloads": 100, # Default Limit
            "downloads_count": 0
        }
        
        # Add Password Hash if provided
        if password and password.strip():
            metadata["password_hash"] = hash_password(password.strip())

        # 6. Save to Redis
        r.hset(file_id, mapping=metadata)
        r.expire(file_id, expiration)

        return {
            "id": file_id,
            "filename": file.filename,
            "message": "File encrypted and stored securely."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download/{file_id}")
@limiter.limit("20/minute") 
async def download_file(
    request: Request, 
    file_id: str,
    password: str = Body(None, embed=True)
):
    file_id = file_id.strip()
    if not r: raise HTTPException(500, "Database Offline")

    # 1. Check Redis
    data = r.hgetall(file_id)
    if not data: raise HTTPException(404, "File expired or not found")

    # 2. Check Password
    if "password_hash" in data:
        if not password: raise HTTPException(401, "Password required")
        if hash_password(password) != data["password_hash"]:
            raise HTTPException(403, "Wrong password")

    # 3. Check Max Downloads
    current_count = int(data.get("downloads_count", 0))
    max_count = int(data.get("max_downloads", 100))
    
    if current_count >= max_count:
        # Cleanup immediately if limit reached
        r.delete(file_id)
        path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
        if os.path.exists(path): os.remove(path)
        raise HTTPException(410, "Download limit reached (File deleted)")

    # 4. Increment Counter
    r.hincrby(file_id, "downloads_count", 1)

    # 5. Check Disk & Decrypt
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
    if not os.path.exists(file_path): raise HTTPException(404, "File missing from disk")

    try:
        with open(file_path, "rb") as f:
            encrypted_content = f.read()
        cipher = Fernet(data['key'].encode())
        decrypted_content = cipher.decrypt(encrypted_content)
    except:
        raise HTTPException(500, "Decryption Failed")

    return Response(
        content=decrypted_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{data["filename"]}"'}
    )

# --- BACKGROUND CLEANUP TASK ---
CLEANUP_INTERVAL = 300 # 5 Minutes

def cleanup_expired_files():
    """Deletes physical files if they are no longer in Redis (Expired or Max Downloads reached)"""
    while True:
        try:
            if r:
                for filename in os.listdir(UPLOAD_DIR):
                    if not filename.endswith(".enc"): continue

                    file_id = filename.replace(".enc", "")
                    # If ID is not in Redis, it is expired/deleted
                    if not r.exists(file_id):
                        path = os.path.join(UPLOAD_DIR, filename)
                        try:
                            os.remove(path)
                            print(f"🧹 Cleanup: Deleted expired file {filename}")
                        except OSError: pass
        except Exception as e:
            print(f"⚠️ Cleanup Error: {e}")
            
        time.sleep(CLEANUP_INTERVAL)

@app.on_event("startup")
def start_cleanup_thread():
    if r:
        thread = threading.Thread(target=cleanup_expired_files, daemon=True)
        thread.start()