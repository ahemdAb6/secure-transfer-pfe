<script setup>
import { ref, onMounted, computed } from 'vue'
import { Html5Qrcode } from "html5-qrcode"
import axios from 'axios'
import JSZip from 'jszip';
import LoginView from './components/Login.vue'
import AdminView from './components/Admin.vue'

const currentView = ref('login') 
const userSession = ref(null) 

const uploadProgress = ref(0)
const recipientEmail = ref('')
const currentTab = ref('upload')
const file = ref(null)
const loading = ref(false)
const result = ref(null)
const error = ref(null)
const fileIdInput = ref('')
const passwordInput = ref('')      
const downloadPassword = ref('')
const expirationTime = ref(86400)
const magicLink = ref('') 
const toast = ref({ show: false, message: '' })
const showPasswordModal = ref(false)
const currentDownloadId = ref(null)
const sentHistory = ref([])
const receivedHistory = ref([])
const isDragging = ref(false) 
let html5QrCode = null

onMounted(() => {
  const savedSession = localStorage.getItem('userSession')
  if (savedSession) {
    const session = JSON.parse(savedSession)
    handleLoginSuccess(session)
  }

  const urlParams = new URLSearchParams(window.location.search)
  const idFromUrl = urlParams.get('id')
  if (idFromUrl) {
    if (userSession.value) {
      currentView.value = 'home'
      switchTab('download')
      fileIdInput.value = idFromUrl
    }
    window.history.replaceState({}, document.title, window.location.pathname)
  }
})

const handleLoginSuccess = (session) => {
  userSession.value = session
  localStorage.setItem('userSession', JSON.stringify(session))
  

  const userSent = localStorage.getItem(`sentHistory_${session.email}`)
  const userReceived = localStorage.getItem(`receivedHistory_${session.email}`)
  
  sentHistory.value = userSent ? JSON.parse(userSent) : []
  receivedHistory.value = userReceived ? JSON.parse(userReceived) : []

  if (session.role === 'ADMIN') {
    currentView.value = 'admin'
    showToast("🛡️ Admin Mode Activated")
  } else {
    currentView.value = 'home'
    showToast(`👋 Welcome ${session.email}`)
  }
}

const handleAdminLogin = (session) => {
  handleLoginSuccess(session)
}

const logout = () => {
  try { fetch('/api/auth/logout', { method: 'POST', body: new FormData().append('session_token', userSession.value?.token) }) } catch(e){}
  
  userSession.value = null
  sentHistory.value = [] 
  receivedHistory.value = []
  localStorage.removeItem('userSession')
  currentView.value = 'login'
}

const switchTab = (tab) => { 
  currentTab.value = tab; 
  error.value = null; 
  fileIdInput.value = ''; 
  passwordInput.value = '';  
  recipientEmail.value = '';
}
const showToast = (msg) => { toast.value = { show: true, message: msg }; setTimeout(() => { toast.value.show = false }, 3000) }
const formatFileSize = (bytes) => { if (bytes < 1024) return bytes + ' B'; if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'; return (bytes / 1024 / 1024).toFixed(2) + ' MB' }
const extractId = (input) => { if (!input) return ""; if (input.includes('id=')) return input.split('id=')[1].split('&')[0]; return input.trim() }
const copyToClipboard = (text, msg) => { navigator.clipboard.writeText(text); showToast(msg) }

const addToSentHistory = (data) => {
  if (!userSession.value) return
  const newItem = { id: data.id, name: data.filename, date: new Date().toLocaleDateString(), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), size: file.value ? formatFileSize(file.value.size) : '?' }
  sentHistory.value.unshift(newItem)
  if (sentHistory.value.length > 20) sentHistory.value.pop()
  localStorage.setItem(`sentHistory_${userSession.value.email}`, JSON.stringify(sentHistory.value))
}

const addToReceivedHistory = (id, filename) => {
  if (!userSession.value || receivedHistory.value.some(item => item.id === id)) return
  const newItem = { id: id, name: filename, date: new Date().toLocaleDateString(), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  receivedHistory.value.unshift(newItem)
  if (receivedHistory.value.length > 20) receivedHistory.value.pop()
  localStorage.setItem(`receivedHistory_${userSession.value.email}`, JSON.stringify(receivedHistory.value))
}

const deleteSentItem = (index) => { 
  sentHistory.value.splice(index, 1); 
  localStorage.setItem(`sentHistory_${userSession.value.email}`, JSON.stringify(sentHistory.value)) 
}
const deleteReceivedItem = (index) => { 
  receivedHistory.value.splice(index, 1); 
  localStorage.setItem(`receivedHistory_${userSession.value.email}`, JSON.stringify(receivedHistory.value)) 
}
const clearReceivedHistory = () => { 
  receivedHistory.value = []; 
  localStorage.removeItem(`receivedHistory_${userSession.value.email}`) 
}


const onDragOver = (e) => { e.preventDefault(); isDragging.value = true }
const onDragLeave = () => { isDragging.value = false }
const onDrop = (e) => { e.preventDefault(); isDragging.value = false; if (e.dataTransfer.files.length > 0) { file.value = e.dataTransfer.files[0]; result.value = null; error.value = null } }
const handleFileChange = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    result.value = null;
    error.value = null;

    if (files.length === 1) {
        file.value = files[0];
    } 
    else {
        console.log("Compressing files...");
        
        const zip = new JSZip();
        
        files.forEach(f => {
            zip.file(f.name, f);
        });
        const zipContent = await zip.generateAsync({ type: "blob" });

        file.value = new File([zipContent], "secure_archive.zip", { 
            type: "application/zip" 
        });
        
        console.log("Compression done! Ready to upload.");
    }

   
    e.target.value = ''; 
};
const handleInputPaste = () => { setTimeout(() => { fileIdInput.value = extractId(fileIdInput.value) }, 100) }

// --- UPLOAD ---
const uploadFile = async () => {
  if (!file.value) return showToast("⚠️ Select a file first")
  
  loading.value = true; 
  result.value = null; 
  error.value = null;
  uploadProgress.value = 0;

  const CHUNK_SIZE = 1024 * 1024 * 5; 
  const totalSize = file.value.size;
  const totalChunks = Math.ceil(totalSize / CHUNK_SIZE);

  try {
    showToast("🚀 Starting upload...")
    const initRes = await axios.post('/api/upload/init', {
        filename: file.value.name,
        total_size: totalSize,
        session_token: userSession.value.token
    });
    const uploadId = initRes.data.upload_id;

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        const start = chunkIndex * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, totalSize);
        const chunk = file.value.slice(start, end); 

        const formData = new FormData();
        formData.append("upload_id", uploadId);
        formData.append("chunk_index", chunkIndex);
        formData.append("file", chunk);

        await axios.post('/api/upload/chunk', formData);


        const percent = Math.round(((chunkIndex + 1) / totalChunks) * 100);
        uploadProgress.value = percent;
    }


    showToast("🔒 Encrypting & Finalizing...");

    const payload = {
        upload_id: uploadId,
        session_token: userSession.value.token,
        expiration: Number(expirationTime.value), 
        password: passwordInput.value ? passwordInput.value : null,
        recipient_email: recipientEmail.value ? recipientEmail.value : null
    };

    const finalizeRes = await axios.post('/api/upload/finalize', payload);

    const data = finalizeRes.data;
    result.value = data;
    magicLink.value = `${window.location.origin}?id=${data.id}`;
    addToSentHistory(data);
    
    passwordInput.value = '';
    recipientEmail.value = '';
    showToast("✅ File Sent Successfully!");

  } catch (e) {
    console.error(e);
    const msg = e.response?.data?.detail || e.message;

    if (e.response?.status === 401) { 
        logout(); 
        showToast("⚠️ Session Expired");
    } else {
        error.value = msg;
        showToast("❌ " + msg);
    }
  } finally {
    loading.value = false;
    uploadProgress.value = 0;
  }
}
const initiateDownload = async (manualId = null) => {
  let rawInput = manualId || fileIdInput.value
  const id = extractId(rawInput)
  if (!id) return showToast("⚠️ Invalid ID")
  loading.value = true; error.value = null
  try {
    const checkResponse = await fetch(`/api/check/${id}`)
    if (checkResponse.status === 404) throw new Error("⛔ File expired or missing")
    if (!checkResponse.ok) throw new Error("Server Error")
    const meta = await checkResponse.json()
    if (meta.protected) { 
      currentDownloadId.value = id; showPasswordModal.value = true; downloadPassword.value = ''; loading.value = false; return 
    } 
    else { await performDownload(id, null) }
  } catch(e) { error.value = e.message; showToast("❌ " + e.message); loading.value = false }
}

const confirmPassword = () => { showPasswordModal.value = false; performDownload(currentDownloadId.value, downloadPassword.value) }

const performDownload = async (id, pwd) => {
  loading.value = true
  try {
    const headers = { 'Content-Type': 'application/json' }
    const body = pwd ? JSON.stringify({ password: pwd }) : JSON.stringify({})
    const response = await fetch(`/api/download/${id}`, { method: 'POST', headers, body })
    
    if (response.status === 401 || response.status === 403) throw new Error("🔒 Incorrect Password")
    if (response.status === 410) throw new Error("⛔ Download limit reached")
    if (response.status === 500) throw new Error("Server Error")
    if (!response.ok) throw new Error("Download failed")
    
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    
    const disposition = response.headers.get('Content-Disposition')
    let fileName = 'downloaded_file' 

    if (disposition) {
      const modernMatch = disposition.match(/filename\*=utf-8''(.+)/i)
      if (modernMatch && modernMatch[1]) {
        fileName = decodeURIComponent(modernMatch[1])
      } else {
        const legacyMatch = disposition.match(/filename="?([^";]+)"?/i)
        if (legacyMatch && legacyMatch[1]) {
          fileName = legacyMatch[1]
        }
      }
    }

    a.download = fileName.replace(/"/g, '')
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    
    addToReceivedHistory(id, fileName)
    fileIdInput.value = ''
    currentDownloadId.value = null
    downloadPassword.value = ''
    showToast("⬇️ Download started...")

  } catch (e) { 
    error.value = e.message 
    showToast("❌ " + e.message) 
    if (e.message.includes("Password")) { showPasswordModal.value = true } 
  } finally { 
    loading.value = false 
  }
}
</script>

<template>
  <div class="main-layout">
    <div class="background-noise"></div>
    <div class="ambient-glow glow-primary"></div>
    <div class="ambient-glow glow-secondary"></div>

    <Transition name="toast-pop">
      <div v-if="toast.show" class="toast-container">
        <div class="toast-content">
          <span class="toast-dot"></span>
          {{ toast.message }}
        </div>
      </div>
    </Transition>

    <div v-if="currentView === 'login'" class="auth-wrapper">
      <div class="glass-panel auth-panel">
        <LoginView 
          @login-success="handleLoginSuccess" 
          @admin-login="handleAdminLogin"
        />
      </div>
    </div>

    <div v-else-if="currentView === 'admin'" class="glass-container">
      <AdminView 
        :apiKey="userSession?.token" 
        @logout="logout"
        @go-home="currentView = 'home'" 
      />
    </div>

    <div v-else-if="currentView === 'home'" class="app-container">
    
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="logo-wrapper">
            <svg class="logo-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path></svg>
          </div>
          <div class="brand-text">
            <h1>Axelites</h1>
            <span>Transfer</span>
          </div>
        </div>

        <div class="user-card">
          <div class="user-avatar">{{ userSession?.email.charAt(0).toUpperCase() }}</div>
          <div class="user-meta">
            <span class="user-email">{{ userSession?.email }}</span>
            <span class="user-badge">Pro Plan</span>
          </div>
        </div>

        <div class="features-list">
          <div class="feature-row">
            <svg class="f-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>
            <span>End-to-End Encryption</span>
          </div>
          <div class="feature-row">
            <svg class="f-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
            <span>Global Edge Network</span>
          </div>
        </div>

        <div class="sidebar-footer">
          <button @click="logout" class="btn-ghost-danger">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            Sign Out
          </button>
        </div>
      </aside>

      <main class="content-area">
        <nav class="tab-nav">
          <div class="tab-pill" :style="{ transform: currentTab === 'upload' ? 'translateX(0)' : 'translateX(100%)' }"></div>
          <button :class="{ 'tab-active': currentTab === 'upload' }" @click="switchTab('upload')">Upload</button>
          <button :class="{ 'tab-active': currentTab === 'download' }" @click="switchTab('download')">Download</button>
        </nav>

        <Transition name="fade-scale" mode="out-in">
          <div v-if="currentTab === 'upload'" key="upload" class="workspace">
            
            <div 
              class="dropzone" 
              :class="{ 'dragging': isDragging, 'has-file': file }"
              @dragover="onDragOver" 
              @dragleave="onDragLeave" 
              @drop="onDrop" 
              @click="!file && $refs.fileInput.click()"
            >
                <input 
    type="file" 
    multiple 
    ref="fileInput" 
    style="display: none"
    @change="handleFileChange"
  >
              
              <div v-if="!file" class="dz-empty">
                <div class="dz-icon-wrapper">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
                <h3>Drag & Drop file</h3>
                <p>or click to browse (Max 5GB)</p>
              </div>

              <div v-else class="dz-selected">
                <div class="file-icon-card">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                </div>
                <div class="file-info">
                  <span class="file-name">{{ file.name }}</span>
                  <span class="file-size">{{ formatFileSize(file.size) }}</span>
                </div>
                <button class="btn-icon-remove" @click.stop="file = null; result = null">✕</button>
              </div>
            </div>

            <div v-if="file && !result" class="settings-panel">
              <div class="form-grid">
                <div class="form-group">
                  <label>Expiration</label>
                  <div class="select-wrapper">
                    <select v-model="expirationTime">
                      <option :value="3600">1 Hour</option>
                      <option :value="86400">24 Hours</option>
                      <option :value="259200">3 Days</option>
                    </select>
                    <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>

                <div class="form-group full-width">
                   <label>Password Protection <span class="opt">(Optional)</span></label>
                   <div class="password-wrapper">
                     <input type="password" v-model="passwordInput" placeholder="Set a secure password..." class="input-field">
                     <button type="button" class="eye-toggle" 
                       @click="$event.target.closest('.password-wrapper').querySelector('input').type = $event.target.closest('.password-wrapper').querySelector('input').type === 'password' ? 'text' : 'password'">
                       👁️
                     </button>
                   </div>
                </div>

                <div class="form-group full-width">
                   <label>Send via Email <span class="opt">(Optional)</span></label>
                   <div class="input-wrapper">
                     <input type="email" v-model="recipientEmail" placeholder="recipient@example.com" class="input-field">
                   </div>
                </div>
              </div>

              <button class="btn-primary-lg btn-upload-pro" @click="uploadFile" :disabled="loading">
                <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
                <span class="btn-content">
                    <span v-if="loading">Uploading... {{ uploadProgress }}%</span>
                    <span v-else>Encrypt & Send File</span>
                </span>
              </button>

            </div>

            <div v-if="result" class="success-card">
              <div class="success-header">
                <div class="success-icon">✓</div>
                <h3>Transfer Ready</h3>
              </div>
              
              <div class="copy-field">
                <input type="text" readonly :value="magicLink">
                <button @click="copyToClipboard(magicLink, 'Link Copied!')">Copy</button>
              </div>

              <div class="actions-row">
                 <button class="btn-secondary" @click="copyToClipboard(result.id, 'ID Copied!')">
                    <span>ID:</span> <span class="mono">{{ result.id }}</span>
                 </button>
                 <div class="qr-thumbnail-wrapper">
                    <img :src="`https://api.qrserver.com/v1/create-qr-code/?size=150x150&color=6366f1&bgcolor=eef2ff&data=${encodeURIComponent(magicLink)}`" alt="QR" class="qr-img" />
                 </div>
              </div>

              <button class="btn-text" @click="file = null; result = null">Send another file</button>
            </div>
            
            <div v-if="error" class="error-msg">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>{{ error }}</span>
            </div>

            <div v-if="sentHistory.length > 0 && !file && !result" class="history-block">
              <h4>Recent Uploads</h4>
              <ul>
                <li v-for="(item, index) in sentHistory" :key="item.id">
                  <div class="history-meta">
                    <span class="h-name">{{ item.name }}</span>
                    <span class="h-date">{{ item.date }} • {{ item.size }}</span>
                  </div>
                  <button class="btn-history-del" @click="deleteSentItem(index)">✕</button>
                </li>
              </ul>
            </div>
          </div>
        </Transition>

        <Transition name="fade-scale" mode="out-in">
          <div v-if="currentTab === 'download'" key="download" class="workspace centered-ws">
            <div class="download-container">
              <div class="download-header">
                <h2>Receive Files</h2>
                <p>Enter a file ID or scan a QR code to download securely.</p>
              </div>

              <div class="input-combo">
                <input v-model="fileIdInput" @input="handleInputPaste" type="text" placeholder="Paste File ID..." class="input-field-lg">
                <button class="btn-scan" title="Scan QR">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                </button>
              </div>

              <button class="btn-primary-lg download-action" @click="() => initiateDownload()" :disabled="loading">
                 <span v-if="loading" class="spinner-svg"></span>
                 <span v-else>Download File</span>
              </button>

              <div v-if="error" class="error-msg">{{ error }}</div>
            </div>

            <div v-if="receivedHistory.length > 0" class="history-block">
              <div class="h-head">
                <h4>Received Files</h4>
                <button @click="clearReceivedHistory">Clear</button>
              </div>
              <ul>
                <li v-for="(item, index) in receivedHistory" :key="item.id" @click="initiateDownload(item.id)" class="clickable">
                  <div class="icon-box-sm">↓</div>
                  <div class="history-meta">
                    <span class="h-name">{{ item.name }}</span>
                    <span class="h-date">{{ item.date }}</span>
                  </div>
                  <button class="btn-history-del" @click.stop="deleteReceivedItem(index)">✕</button>
                </li>
              </ul>
            </div>
          </div>
        </Transition>

      </main>
    </div>

    <Transition name="modal">
      <div v-if="showPasswordModal" class="modal-backdrop">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Locked File</h3>
            <button @click="showPasswordModal = false">✕</button>
          </div>
          <p class="modal-desc">This file is password protected.</p>
          
          <div class="password-wrapper modal-input">
             <input type="password" v-model="downloadPassword" class="input-field" placeholder="Enter Password" autofocus>
             <button type="button" class="eye-toggle" 
               @click="$event.target.closest('.password-wrapper').querySelector('input').type = $event.target.closest('.password-wrapper').querySelector('input').type === 'password' ? 'text' : 'password'">
               👁️
             </button>
          </div>

          <button class="btn-primary-lg" @click="confirmPassword">Unlock & Download</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg-dark: #020617;
  --bg-panel: #0f172a;
  --bg-surface: #1e293b;
  --bg-hover: #334155;
  --border: rgba(255, 255, 255, 0.08);
  --border-light: rgba(255, 255, 255, 0.15);
  
  --primary: #6366f1;
  --primary-glow: rgba(99, 102, 241, 0.4);
  --accent: #10b981;  
  
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
  
  --radius-lg: 16px;
  --radius-md: 8px;
  --radius-sm: 6px;
  
  --shadow-card: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  --shadow-glow: 0 0 20px rgba(99, 102, 241, 0.15);
}

.main-layout {
  position: relative;
  width: 100vw;
  height: 100vh;
  background-color: var(--bg-dark);
  color: var(--text-main);
  font-family: 'Inter', sans-serif;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
}

.background-noise {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  z-index: 0;
  pointer-events: none;
}

.ambient-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  z-index: 0;
  animation: float 20s infinite ease-in-out;
}
.glow-primary { width: 500px; height: 500px; background: #4f46e5; opacity: 0.15; top: -20%; left: -10%; }
.glow-secondary { width: 400px; height: 400px; background: #0ea5e9; opacity: 0.1; bottom: -20%; right: -10%; animation-delay: -5s; }

@keyframes float { 0%, 100% { transform: translate(0, 0); } 50% { transform: translate(30px, -30px); } }

.app-container, .auth-wrapper {
  position: relative;
  z-index: 10;
  display: flex;
  width: 95%;
  max-width: 1100px;
  height: 800px;
  max-height: 90vh;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 0 0 1px rgba(255,255,255,0.05);
  overflow: hidden;
}

.auth-wrapper { justify-content: center; align-items: center; background: none; border: none; box-shadow: none; backdrop-filter: none; }
.auth-panel { width: 100%; max-width: 440px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 24px; padding: 40px; box-shadow: var(--shadow-glow); }

.sidebar {
  width: 280px;
  background: rgba(2, 6, 23, 0.4);
  border-right: 1px solid var(--border);
  padding: 32px;
  display: flex;
  flex-direction: column;
}

.sidebar-header { display: flex; align-items: center; gap: 12px; margin-bottom: 40px; }
.logo-wrapper { width: 40px; height: 40px; background: linear-gradient(135deg, var(--primary), #818cf8); border-radius: 10px; display: grid; place-items: center; color: white; box-shadow: 0 0 15px rgba(99, 102, 241, 0.4); }
.logo-svg { width: 24px; height: 24px; }
.brand-text h1 { font-size: 1.1rem; font-weight: 700; letter-spacing: -0.02em; }
.brand-text span { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

.user-card { display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 12px; margin-bottom: 32px; border: 1px solid var(--border); }
.user-avatar { width: 32px; height: 32px; background: var(--accent); color: #064e3b; border-radius: 50%; font-weight: 700; display: grid; place-items: center; font-size: 0.9rem; }
.user-meta { display: flex; flex-direction: column; }
.user-email { font-size: 0.85rem; font-weight: 500; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-badge { font-size: 0.7rem; color: var(--accent); font-weight: 600; letter-spacing: 0.02em; }

.features-list { display: flex; flex-direction: column; gap: 16px; flex: 1; }
.feature-row { display: flex; align-items: center; gap: 12px; color: var(--text-muted); font-size: 0.9rem; font-weight: 500; }
.f-icon { width: 18px; height: 18px; color: var(--text-dim); }

.sidebar-footer { margin-top: auto; }
.btn-ghost-danger { width: 100%; display: flex; align-items: center; gap: 10px; padding: 10px; background: none; border: none; color: #ef4444; cursor: pointer; font-size: 0.9rem; font-weight: 500; border-radius: 8px; transition: 0.2s; opacity: 0.8; }
.btn-ghost-danger:hover { background: rgba(239, 68, 68, 0.1); opacity: 1; }

.content-area { flex: 1; padding: 40px; display: flex; flex-direction: column; overflow-y: auto; background: linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%); }

.tab-nav { position: relative; display: flex; background: var(--bg-surface); padding: 4px; border-radius: 12px; width: fit-content; margin: 0 auto 40px; border: 1px solid var(--border); }
.tab-pill { position: absolute; top: 4px; left: 4px; width: calc(50% - 4px); height: calc(100% - 8px); background: var(--bg-hover); border-radius: 8px; transition: transform 0.25s cubic-bezier(0.2, 0, 0, 1); border: 1px solid rgba(255,255,255,0.05); }
.tab-nav button { flex: 1; position: relative; z-index: 1; background: none; border: none; padding: 8px 32px; color: var(--text-muted); font-size: 0.9rem; font-weight: 500; cursor: pointer; transition: color 0.2s; min-width: 120px; }
.tab-nav button.tab-active { color: white; font-weight: 600; }

.workspace { max-width: 500px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 24px; }
.centered-ws { align-items: center; }

.dropzone {
  position: relative;
  height: 240px;
  border: 1px dashed var(--border-light);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.01);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  overflow: hidden;
}
.dropzone:hover { border-color: var(--primary); background: rgba(99, 102, 241, 0.02); }
.dropzone.dragging { border-color: var(--primary); background: rgba(99, 102, 241, 0.05); transform: scale(1.02); box-shadow: 0 0 30px rgba(99, 102, 241, 0.1); }
.dropzone.has-file { border-style: solid; border-color: var(--border); background: var(--bg-surface); }

.dz-empty { text-align: center; color: var(--text-muted); }
.dz-icon-wrapper { width: 56px; height: 56px; background: rgba(255,255,255,0.03); border-radius: 16px; display: grid; place-items: center; margin: 0 auto 16px; color: var(--text-dim); transition: 0.3s; }
.dropzone:hover .dz-icon-wrapper { color: var(--primary); transform: translateY(-4px); }
.dz-empty h3 { font-size: 1rem; color: var(--text-main); margin-bottom: 4px; }
.dz-empty p { font-size: 0.85rem; color: var(--text-dim); }

.dz-selected { width: 100%; padding: 20px; display: flex; align-items: center; gap: 16px; }
.file-icon-card { width: 48px; height: 48px; background: var(--primary); color: white; border-radius: 10px; display: grid; place-items: center; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }
.file-info { flex: 1; display: flex; flex-direction: column; }
.file-name { font-weight: 600; font-size: 0.95rem; color: white; }
.file-size { font-size: 0.8rem; color: var(--text-muted); margin-top: 2px; }
.btn-icon-remove { background: transparent; border: 1px solid var(--border); width: 28px; height: 28px; border-radius: 50%; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: 0.2s; font-size: 12px; }
.btn-icon-remove:hover { background: rgba(255,255,255,0.1); color: white; }

.settings-panel { animation: slideUp 0.4s ease; }
.form-grid { display: grid; grid-template-columns: 1fr; gap: 16px; margin-bottom: 24px; }
.form-group label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; letter-spacing: 0.02em; }
.form-group .opt { font-weight: 400; color: var(--text-dim); }
.select-wrapper { position: relative; }
.select-wrapper select, .input-field { width: 100%; background: var(--bg-surface); border: 1px solid var(--border); padding: 12px 14px; border-radius: 10px; color: white; font-size: 0.95rem; outline: none; transition: 0.2s; appearance: none; font-family: 'Inter', sans-serif; }
.select-wrapper select:focus, .input-field:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2); }
.chevron { position: absolute; right: 14px; top: 50%; transform: translateY(-50%); width: 16px; color: var(--text-muted); pointer-events: none; }

.password-wrapper { position: relative; display: flex; align-items: center; }
.eye-toggle { position: absolute; right: 12px; background: none; border: none; cursor: pointer; font-size: 1.1rem; opacity: 0.6; transition: 0.2s; }
.eye-toggle:hover { opacity: 1; transform: scale(1.1); }

/* --- NOUVEAU STYLE POUR LE BOUTON AVEC PROGRESSION --- */
.btn-primary-lg { position: relative; width: 100%; height: 50px; background: linear-gradient(180deg, #6366f1 0%, #4f46e5 100%); border: none; border-radius: 12px; color: white; font-weight: 600; font-size: 1rem; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.1), inset 0 1px 0 rgba(255,255,255,0.2); transition: all 0.2s; display: flex; justify-content: center; align-items: center; overflow: hidden; }
.btn-primary-lg:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4); }
.btn-primary-lg:disabled { opacity: 0.9; cursor: not-allowed; }

/* La "liquide" qui monte ou remplit le bouton */
.btn-upload-pro .progress-fill {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  background: rgba(0, 0, 0, 0.2); /* Un fond plus sombre qui avance */
  z-index: 1;
  transition: width 0.2s linear;
}
.btn-content {
  position: relative;
  z-index: 2; /* Le texte reste au dessus */
  display: flex;
  align-items: center;
  gap: 10px;
}

.spinner-svg { width: 20px; height: 20px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.success-card { background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 16px; padding: 24px; text-align: center; animation: slideUp 0.4s ease; }
.success-header { display: flex; flex-direction: column; align-items: center; gap: 12px; margin-bottom: 20px; }
.success-icon { width: 32px; height: 32px; background: var(--accent); color: #022c22; border-radius: 50%; display: grid; place-items: center; font-weight: 800; font-size: 14px; }
.success-header h3 { color: var(--accent); font-size: 1.1rem; }
.copy-field { display: flex; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 8px; padding: 4px; margin-bottom: 16px; }
.copy-field input { flex: 1; background: none; border: none; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; padding: 0 12px; outline: none; }
.copy-field button { background: var(--bg-surface); border: 1px solid var(--border); color: white; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; font-weight: 500; transition: 0.2s; }
.copy-field button:hover { background: var(--bg-hover); }

.actions-row { display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 20px; }
.btn-secondary { background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text-main); padding: 8px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 0.9rem; transition: 0.2s; }
.btn-secondary:hover { background: rgba(255,255,255,0.1); }
.btn-secondary .mono { font-family: 'JetBrains Mono', monospace; color: var(--accent); }
.qr-thumbnail-wrapper { background: white; padding: 4px; border-radius: 8px; display: flex; }
.qr-img { width: 32px; height: 32px; cursor: zoom-in; }
.btn-text { background: none; border: none; color: var(--text-dim); font-size: 0.85rem; cursor: pointer; text-decoration: underline; text-decoration-color: rgba(255,255,255,0.2); }

.download-container { text-align: center; width: 100%; max-width: 440px; }
.download-header h2 { font-size: 1.8rem; margin-bottom: 8px; background: linear-gradient(to right, white, #cbd5e1); -webkit-background-clip: text; color: transparent; }
.download-header p { color: var(--text-muted); font-size: 0.95rem; margin-bottom: 32px; }

.input-combo { display: flex; gap: 10px; margin-bottom: 24px; }
.input-field-lg { flex: 1; background: var(--bg-surface); border: 1px solid var(--border); padding: 14px 16px; border-radius: 12px; color: white; font-size: 1rem; outline: none; transition: 0.2s; }
.input-field-lg:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); }
.btn-scan { width: 50px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 12px; color: var(--text-main); cursor: pointer; display: grid; place-items: center; transition: 0.2s; }
.btn-scan:hover { background: rgba(255,255,255,0.1); color: var(--accent); }
.download-action { background: linear-gradient(180deg, #10b981 0%, #059669 100%); }
.download-action:hover { box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); }

.history-block { margin-top: 32px; border-top: 1px solid var(--border); padding-top: 24px; width: 100%; }
.h-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.history-block h4 { font-size: 0.75rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.05em; font-weight: 600; }
.history-block button { background: none; border: none; color: var(--text-dim); font-size: 0.75rem; cursor: pointer; }
.history-block ul { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.history-block li { display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 8px; transition: 0.2s; border: 1px solid transparent; }
.history-block li.clickable:hover { background: rgba(255,255,255,0.05); border-color: var(--border); cursor: pointer; }
.history-meta { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.h-name { font-size: 0.9rem; font-weight: 500; color: var(--text-main); }
.h-date { font-size: 0.75rem; color: var(--text-dim); }
.btn-history-del { color: var(--text-dim); opacity: 0; transition: 0.2s; font-size: 14px; }
.history-block li:hover .btn-history-del { opacity: 1; }
.icon-box-sm { width: 24px; height: 24px; background: rgba(16, 185, 129, 0.1); color: var(--accent); border-radius: 6px; display: grid; place-items: center; font-size: 12px; }

.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(8px); z-index: 100; display: grid; place-items: center; }
.modal-card { background: #1e293b; border: 1px solid var(--border-light); width: 90%; max-width: 400px; padding: 24px; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); animation: scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header h3 { font-size: 1.2rem; }
.modal-header button { background: none; border: none; color: var(--text-muted); font-size: 1.2rem; cursor: pointer; }
.modal-desc { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 20px; }
.modal-input { margin-bottom: 20px; }
.scanner-box { width: 100%; height: 250px; background: black; border-radius: 12px; overflow: hidden; border: 1px solid var(--border); }

.toast-container { position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%); z-index: 200; }
.toast-content { background: #0f172a; border: 1px solid var(--border-light); padding: 10px 20px; border-radius: 50px; color: white; font-size: 0.9rem; font-weight: 500; display: flex; align-items: center; gap: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
.toast-dot { width: 8px; height: 8px; background: var(--accent); border-radius: 50%; box-shadow: 0 0 10px var(--accent); }
.toast-pop-enter-active, .toast-pop-leave-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.toast-pop-enter-from, .toast-pop-leave-to { opacity: 0; transform: translate(-50%, 20px); }


.fade-scale-enter-active, .fade-scale-leave-active { transition: all 0.2s ease; }
.fade-scale-enter-from { opacity: 0; transform: scale(0.98); }
.fade-scale-leave-to { opacity: 0; transform: scale(0.98); }
@keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }

@media (max-width: 900px) {
  .app-container { flex-direction: column; height: 100vh; width: 100%; max-width: 100%; border-radius: 0; border: none; }
  .sidebar { width: 100%; height: auto; flex-direction: row; align-items: center; padding: 16px; border-right: none; border-bottom: 1px solid var(--border); background: var(--bg-dark); }
  .sidebar-header { margin-bottom: 0; }
  .user-card, .features-list { display: none; }
  .sidebar-footer { margin-left: auto; margin-top: 0; }
  .content-area { padding: 20px; }
  .tab-nav { width: 100%; margin-bottom: 24px; }
}
</style>