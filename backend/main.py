import shutil
import os
import uuid
import redis
import clamd
import io
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import Response
from cryptography.fernet import Fernet
import threading
import time

app = FastAPI()

# --- CONFIGURATION ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Connexion Redis
r = redis.Redis(host='redis', port=6379, decode_responses=True)

# --- FONCTION DE SÉCURITÉ ---
def scan_file_for_virus(content: bytes):
    """
    Scanne le fichier. Si virus ou erreur antivirus => Lève une exception.
    """
    try:
        # Tenter de se connecter à ClamAV (Nom du service docker: 'clamav')
        cd = clamd.ClamdNetworkSocket('clamav', 3310)
        
        # Vérifier si ClamAV est réveillé
        if cd.ping() != 'PONG':
            raise Exception("L'antivirus ne répond pas (Ping failed)")

        # Scanner le contenu directement en mémoire (Stream)
        # scan_result ressemble à : {'stream': ('FOUND', 'Eicar-Test-Signature')}
        scan_result = cd.instream(io.BytesIO(content))

        if scan_result and 'stream' in scan_result:
            status, virus_name = scan_result['stream']
            if status == 'FOUND':
                # 🚨 VIRUS TROUVÉ -> ON BLOQUE TOUT
                print(f"🚨 ALERTE SÉCURITÉ : {virus_name}")
                raise HTTPException(status_code=400, detail=f"VIRUS DÉTECTÉ : {virus_name}")

    except HTTPException as he:
        # Si c'est notre erreur 400 (Virus), on la laisse passer
        raise he
    except Exception as e:
        # Si ClamAV est éteint ou bugué, on refuse l'upload par sécurité
        print(f"❌ Erreur technique Antivirus : {str(e)}")
        # IMPORTANT : On bloque si on n'est pas sûr
        raise HTTPException(status_code=503, detail="Service Antivirus indisponible. Upload bloqué par sécurité.")

@app.get("/")
def read_root():
    return {"status": "Secure Server Running"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...), 
    expiration: int = Form(86400)
):
    try:
        # 1. Lire le fichier en mémoire (RAM)
        file_content = await file.read()

        # 2. SCANNER IMMÉDIATEMENT (Avant chiffrement, avant sauvegarde)
        # Si virus -> Ça plante ici et s'arrête.
        scan_file_for_virus(file_content)

        # --- Si on arrive ici, le fichier est PROPRE ---

        # 3. Chiffrement (AES)
        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted_content = cipher.encrypt(file_content)

        # 4. Sauvegarde Sécurisée (.enc)
        file_id = str(uuid.uuid4())
        secure_filename = f"{file_id}.enc"
        file_location = os.path.join(UPLOAD_DIR, secure_filename)

        with open(file_location, "wb") as f:
            f.write(encrypted_content)

        # 5. Enregistrement Redis
        r.hset(file_id, mapping={
            "filename": file.filename,
            "key": key.decode()
        })
        r.expire(file_id, expiration)

        return {
            "id": file_id,
            "filename": file.filename,
            "message": "Fichier sain, chiffré et transféré."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    file_id = file_id.strip()
    
    # Vérification classique
    data = r.hgetall(file_id)
    if not data:
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    original_filename = data['filename']
    key = data['key'].encode()
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.enc")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Fichier perdu")

    with open(file_path, "rb") as f:
        encrypted_content = f.read()

    try:
        cipher = Fernet(key)
        decrypted_content = cipher.decrypt(encrypted_content)
    except:
        raise HTTPException(status_code=500, detail="Erreur de déchiffrement")

    return Response(
        content=decrypted_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{original_filename}"'}
    )

CLEANUP_INTERVAL = 300  # 5 minutes

def cleanup_expired_files():
    while True:
        try:
            for filename in os.listdir(UPLOAD_DIR):
                if not filename.endswith(".enc"):
                    continue

                file_id = filename.replace(".enc", "")
                
                # Si la clé Redis n'existe plus => fichier expiré
                if not r.exists(file_id):
                    file_path = os.path.join(UPLOAD_DIR, filename)
                    try:
                        os.remove(file_path)
                        print(f"🧹 Fichier expiré supprimé : {filename}")
                    except Exception as e:
                        print(f"❌ Erreur suppression {filename} : {e}")

        except Exception as e:
            print(f"❌ Erreur cleanup : {e}")

        time.sleep(CLEANUP_INTERVAL)


@app.on_event("startup")
def start_cleanup_thread():
    thread = threading.Thread(target=cleanup_expired_files, daemon=True)
    thread.start()
