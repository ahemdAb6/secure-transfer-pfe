<script setup>
import { ref, onMounted } from 'vue'
import { Html5Qrcode } from "html5-qrcode"

// --- STATE (Variables) ---
const currentTab = ref('upload')
const file = ref(null)
const loading = ref(false)
const result = ref(null)      // Only for Sender
const error = ref(null)
const fileIdInput = ref('')   // Only for Receiver
const expirationTime = ref(86400)
const magicLink = ref('') 
const toast = ref({ show: false, message: '' })
const showScanner = ref(false)
const sentHistory = ref([])
const receivedHistory = ref([])
const isDragging = ref(false) // UI Drag state
let html5QrCode = null

// --- LIFECYCLE ---
onMounted(() => {
  // Load History
  const savedSent = localStorage.getItem('sentHistory')
  const savedReceived = localStorage.getItem('receivedHistory')
  if (savedSent) sentHistory.value = JSON.parse(savedSent)
  if (savedReceived) receivedHistory.value = JSON.parse(savedReceived)

  // Check URL for download ID
  const urlParams = new URLSearchParams(window.location.search)
  const idFromUrl = urlParams.get('id')
  if (idFromUrl) {
    switchTab('download')
    fileIdInput.value = idFromUrl
    // Clean URL
    window.history.replaceState({}, document.title, window.location.pathname)
  }
})

// --- LOGIC: Strict Tab Switching ---
const switchTab = (tab) => {
  currentTab.value = tab
  error.value = null
  // We do not clear inputs to avoid annoyance, but we ensure states don't mix
}

// --- UTILS ---
const showToast = (msg) => {
  toast.value = { show: true, message: msg }
  setTimeout(() => { toast.value.show = false }, 3000)
}

const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

const extractId = (input) => {
  if (!input) return ""
  if (input.includes('id=')) return input.split('id=')[1].split('&')[0]
  return input.trim()
}

const copyToClipboard = (text, msg) => { navigator.clipboard.writeText(text); showToast(msg) }

// --- HISTORY MANAGEMENT ---
const addToSentHistory = (data) => {
  const newItem = {
    id: data.id,
    name: data.filename,
    date: new Date().toLocaleDateString(),
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    size: file.value ? formatFileSize(file.value.size) : '?'
  }
  sentHistory.value.unshift(newItem)
  if (sentHistory.value.length > 20) sentHistory.value.pop()
  localStorage.setItem('sentHistory', JSON.stringify(sentHistory.value))
}

const addToReceivedHistory = (id, filename) => {
  if (receivedHistory.value.some(item => item.id === id)) return
  const newItem = {
    id: id,
    name: filename,
    date: new Date().toLocaleDateString(),
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  receivedHistory.value.unshift(newItem)
  if (receivedHistory.value.length > 20) receivedHistory.value.pop()
  localStorage.setItem('receivedHistory', JSON.stringify(receivedHistory.value))
}

const deleteSentItem = (index) => {
  sentHistory.value.splice(index, 1); localStorage.setItem('sentHistory', JSON.stringify(sentHistory.value))
}
const deleteReceivedItem = (index) => {
  receivedHistory.value.splice(index, 1); localStorage.setItem('receivedHistory', JSON.stringify(receivedHistory.value))
}
const clearReceivedHistory = () => {
  receivedHistory.value = []; localStorage.removeItem('receivedHistory')
}

// --- DRAG & DROP ---
const onDragOver = (e) => { e.preventDefault(); isDragging.value = true }
const onDragLeave = () => { isDragging.value = false }
const onDrop = (e) => {
  e.preventDefault(); isDragging.value = false
  if (e.dataTransfer.files.length > 0) { file.value = e.dataTransfer.files[0]; result.value = null; error.value = null }
}
const handleFileChange = (e) => { file.value = e.target.files[0]; result.value = null; error.value = null }
const handleInputPaste = () => { setTimeout(() => { fileIdInput.value = extractId(fileIdInput.value) }, 100) }

// --- API: UPLOAD (Sender Only) ---
const uploadFile = async () => {
  if (!file.value) return showToast("⚠️ Select a file first")
  
  loading.value = true
  result.value = null // RESET: No link yet
  error.value = null

  const formData = new FormData()
  formData.append("file", file.value)
  formData.append("expiration", expirationTime.value)

  try {
    const response = await fetch('/api/upload', { method: 'POST', body: formData })
    
    // Handle Errors (Virus 400, Server 500)
    if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.detail || `Upload Failed (${response.status})`)
    }

    const data = await response.json()
    
    // SUCCESS: Only create link now
    result.value = data
    magicLink.value = `${window.location.origin}?id=${data.id}`
    addToSentHistory(data)
    
    // STRICT SEPARATION: DO NOT TOUCH fileIdInput
    
    showToast("✅ File Sent Successfully!")

  } catch (e) {
    result.value = null // Ensure no result shown
    error.value = e.message
    showToast("❌ " + e.message)
  } finally {
    loading.value = false
  }
}

// --- API: DOWNLOAD (Receiver Only) ---
const downloadFile = async (manualId = null) => {
  let rawInput = manualId || fileIdInput.value
  const id = extractId(rawInput)

  if (!manualId) fileIdInput.value = id
  if (!id) return showToast("⚠️ Invalid ID")
  
  loading.value = true
  error.value = null 

  try {
    const response = await fetch(`/api/download/${id}`)
    
    // SPECIFIC ERROR HANDLING
    if (response.status === 500) throw new Error("Server Error: File corrupted or decryption failed.")
    if (response.status === 404) throw new Error("⛔ File expired or missing")
    if (!response.ok) throw new Error("Download failed")

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    
    const disposition = response.headers.get('Content-Disposition')
    let fileName = 'file'
    if (disposition && disposition.match(/filename="?(.+)"?/)) {
      fileName = disposition.match(/filename="?(.+)"?/)[1]
    }
    a.download = fileName.replace(/"/g, '')
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    
    addToReceivedHistory(id, fileName)
    
    // ✅ FIX: Clear input only after success
    fileIdInput.value = ''
    
    showToast("⬇️ Download started...")

  } catch (e) {
    console.error("DL Error:", e)
    error.value = e.message
    showToast("❌ " + e.message)
  } finally {
    loading.value = false
  }
}

// --- SCANNER ---
const startScanner = () => {
  showScanner.value = true; error.value = null
  setTimeout(() => {
    if (html5QrCode) { try { html5QrCode.stop(); html5QrCode.clear() } catch(e){} }
    html5QrCode = new Html5Qrcode("reader")
    html5QrCode.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 250, height: 250 } }, 
      (decodedText) => { stopScanner(); const cleanID = extractId(decodedText); fileIdInput.value = cleanID; showToast("✅ Code Detected!"); downloadFile(cleanID) },
      (err) => {}
    ).catch(err => { showScanner.value = false; showToast("❌ Camera Error") })
  }, 300)
}
const stopScanner = () => {
  if (html5QrCode) { html5QrCode.stop().then(() => { html5QrCode.clear(); showScanner.value = false }).catch(() => { showScanner.value = false }) } else { showScanner.value = false }
}
</script>

<template>
  <div class="main-layout">
    
    <!-- Background Elements -->
    <div class="ambient-bg"></div>
    <div class="ambient-orb orb-1"></div>
    <div class="ambient-orb orb-2"></div>

    <!-- Toast Notification -->
    <Transition name="slide-fade">
      <div v-if="toast.show" class="toast">{{ toast.message }}</div>
    </Transition>

    <!-- Scanner Modal -->
    <Transition name="fade">
      <div v-if="showScanner" class="modal-overlay">
        <div class="scanner-card">
          <div class="scanner-header">
            <h3>Scan QR Code</h3>
            <button @click="stopScanner" class="close-icon">✕</button>
          </div>
          <div id="reader" class="qr-reader-box"></div>
          <p class="scanner-hint">Point camera at the transfer QR code</p>
        </div>
      </div>
    </Transition>

    <!-- App Content -->
    <div class="glass-container">
      
      <!-- LEFT PANEL: Brand & Value Prop -->
      <aside class="left-panel">
        <div class="brand">
          <div class="logo-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="logo-svg">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>
            </svg>
          </div>
          <span class="brand-name">SecureTransfer</span>
        </div>

        <div class="hero-text">
          <h1>Transfer files<br><span class="text-gradient">Security First.</span></h1>
          <p>End-to-end encrypted file sharing. No logs. No accounts. Files are automatically destroyed after expiry.</p>
        </div>

        <div class="features-grid">
          <div class="feature-item">
            <span class="f-icon">🔒</span>
            <span>AES-256 Encryption</span>
          </div>
          <div class="feature-item">
            <span class="f-icon">⚡</span>
            <span>High Speed CDN</span>
          </div>
          <div class="feature-item">
            <span class="f-icon">👻</span>
            <span>Ephemeral Storage</span>
          </div>
        </div>

        <div class="footer-note">
          <p>&copy; 2024 SecureTransfer Inc. Privacy Focused.</p>
        </div>
      </aside>

      <!-- RIGHT PANEL: Interactive Interface -->
      <main class="right-panel">
        
        <!-- Tab Switcher -->
        <nav class="tab-switcher">
          <div 
            class="tab-bg" 
            :style="{ transform: currentTab === 'upload' ? 'translateX(0)' : 'translateX(100%)' }"
          ></div>
          <button 
            :class="{ active: currentTab === 'upload' }" 
            @click="switchTab('upload')"
          >
            Send File
          </button>
          <button 
            :class="{ active: currentTab === 'download' }" 
            @click="switchTab('download')"
          >
            Receive File
          </button>
        </nav>

        <!-- UPLOAD VIEW -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'upload'" key="upload" class="panel-content">
            
            <!-- Drag & Drop Zone -->
            <div 
              class="drop-zone" 
              :class="{ 'dragging': isDragging, 'has-file': file }"
              @dragover="onDragOver"
              @dragleave="onDragLeave"
              @drop="onDrop"
              @click="!file && $refs.fileInput.click()"
            >
              <input type="file" ref="fileInput" @change="handleFileChange" hidden>
              
              <div v-if="!file" class="dz-content">
                <div class="dz-icon-circle">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                  </svg>
                </div>
                <h3>Drop file here or browse</h3>
                <p>Supports all file formats up to 5GB</p>
              </div>

              <div v-else class="file-preview">
                <div class="file-icon">📄</div>
                <div class="file-details">
                  <span class="fn">{{ file.name }}</span>
                  <span class="fs">{{ formatFileSize(file.size) }}</span>
                </div>
                <button class="remove-file" @click.stop="file = null; result = null">✕</button>
              </div>
            </div>

            <!-- Settings & Action -->
            <div v-if="file && !result" class="settings-box">
              <div class="setting-row">
                <label>Auto-Destruct Timer</label>
                <div class="select-wrapper">
                  <select v-model="expirationTime">
                    <option :value="3600">1 Hour</option>
                    <option :value="86400">24 Hours</option>
                    <option :value="259200">3 Days</option>
                    <option :value="604800">7 Days (Premium)</option>
                    <option :value="2592000">30 Days (Premium)</option>
                  </select>
                </div>
              </div>
              
              <button class="primary-btn" @click="uploadFile" :disabled="loading">
                <span v-if="loading" class="spinner"></span>
                {{ loading ? 'Encrypting & Uploading...' : 'Secure Transfer' }}
              </button>
            </div>

            <!-- Result Screen -->
            <div v-if="result" class="result-box">
              <div class="result-header">
                <div class="check-icon">✓</div>
                <h3>File Ready to Share</h3>
              </div>
              
              <div class="link-box">
                <input type="text" readonly :value="magicLink">
                <button @click="copyToClipboard(magicLink, 'Lien copié !')">Copy Link</button>
              </div>
              
              <div class="meta-actions">
                 <div class="id-pill" @click="copyToClipboard(result.id, 'ID copié !')">
                   <span>ID: {{ result.id }}</span>
                   <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                 </div>
                 <div class="qr-trigger">
                    <img :src="`https://api.qrserver.com/v1/create-qr-code/?size=150x150&color=6366f1&bgcolor=eef2ff&data=${encodeURIComponent(magicLink)}`" alt="QR" class="qr-mini" />
                 </div>
              </div>

              <button class="reset-btn" @click="file = null; result = null">Send Another File</button>
            </div>

             <!-- Error Message -->
            <div v-if="error" class="error-banner">
              <span>⚠️ {{ error }}</span>
            </div>

            <!-- Upload History -->
            <div v-if="sentHistory.length > 0 && !file && !result" class="history-section">
              <h4>Recent Uploads</h4>
              <ul class="history-list">
                <li v-for="(item, index) in sentHistory" :key="item.id">
                  <div class="h-left">
                    <div class="h-icon sent">↑</div>
                    <div class="h-info">
                      <span class="h-name">{{ item.name }}</span>
                      <span class="h-date">{{ item.date }} • {{ item.time }}</span>
                    </div>
                  </div>
                  <button class="h-del" @click="deleteSentItem(index)">✕</button>
                </li>
              </ul>
            </div>

          </div>
        </Transition>

        <!-- DOWNLOAD VIEW -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'download'" key="download" class="panel-content">
            
            <div class="download-card">
              <h2>Receive File</h2>
              <p>Enter the secure ID or paste the full link to decrypt and download.</p>
              
              <div class="input-group">
                <input 
                  v-model="fileIdInput" 
                  @input="handleInputPaste" 
                  type="text" 
                  placeholder="Paste ID or Link here..."
                >
                <button class="scan-trigger" @click="startScanner">
                   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7V5a2 2 0 0 1 2-2h2"></path><path d="M17 3h2a2 2 0 0 1 2 2v2"></path><path d="M21 17v2a2 2 0 0 1-2 2h-2"></path><path d="M7 21H5a2 2 0 0 1-2-2v-2"></path></svg>
                </button>
              </div>

              <button class="primary-btn download-btn" @click="() => downloadFile()" :disabled="loading">
                <span v-if="loading" class="spinner"></span>
                {{ loading ? 'Retrieving File...' : 'Download' }}
              </button>

              <div v-if="error" class="error-banner">
                <span>⚠️ {{ error }}</span>
              </div>
            </div>

            <!-- Received History -->
            <div v-if="receivedHistory.length > 0" class="history-section">
              <div class="h-header">
                <h4>Received Files</h4>
                <button class="clear-btn" @click="clearReceivedHistory">Clear All</button>
              </div>
              <ul class="history-list">
                <li v-for="(item, index) in receivedHistory" :key="item.id" @click="downloadFile(item.id)" class="clickable">
                  <div class="h-left">
                    <div class="h-icon received">↓</div>
                    <div class="h-info">
                      <span class="h-name">{{ item.name }}</span>
                      <span class="h-date">{{ item.date }} • {{ item.time }}</span>
                    </div>
                  </div>
                  <button class="h-del" @click.stop="deleteReceivedItem(index)">✕</button>
                </li>
              </ul>
            </div>

          </div>
        </Transition>

      </main>
    </div>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* --- RESET & BASES --- */
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; -webkit-font-smoothing: antialiased; }

:root {
  --primary: #6366f1; /* Indigo 500 */
  --primary-dark: #4f46e5;
  --accent: #10b981; /* Emerald 500 */
  --bg-dark: #0f172a;
  --bg-card: #1e293b;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --border: rgba(255,255,255,0.1);
  --glass: rgba(30, 41, 59, 0.7);
}

.main-layout {
  position: relative;
  width: 100vw;
  height: 100vh;
  background-color: var(--bg-dark);
  color: var(--text-main);
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

/* --- DYNAMIC BACKGROUND --- */
.ambient-bg {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 15% 50%, #1e1b4b 0%, #0f172a 50%, #020617 100%);
  z-index: 0;
}
.ambient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  animation: float 20s infinite ease-in-out;
}
.orb-1 { width: 400px; height: 400px; background: #4f46e5; top: -100px; left: -100px; }
.orb-2 { width: 500px; height: 500px; background: #0ea5e9; bottom: -150px; right: -150px; animation-delay: -5s; }

@keyframes float {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(50px, 50px); }
}

/* --- GLASS CONTAINER --- */
.glass-container {
  position: relative;
  z-index: 10;
  display: flex;
  width: 90%;
  max-width: 1200px;
  height: 85vh;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255,255,255,0.1);
  backdrop-filter: blur(20px);
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

/* --- LEFT PANEL --- */
.left-panel {
  width: 40%;
  background: rgba(0, 0, 0, 0.2);
  padding: 60px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-right: 1px solid var(--border);
}

.brand { display: flex; align-items: center; gap: 12px; }
.logo-box { width: 40px; height: 40px; background: var(--primary); border-radius: 10px; display: grid; place-items: center; box-shadow: 0 0 15px rgba(99, 102, 241, 0.5); }
.logo-svg { width: 24px; color: white; }
.brand-name { font-weight: 700; font-size: 1.5rem; letter-spacing: -0.5px; }

.hero-text h1 { font-size: 3.5rem; line-height: 1.1; font-weight: 800; margin-bottom: 20px; }
.text-gradient { background: linear-gradient(to right, #818cf8, #2dd4bf); -webkit-background-clip: text; color: transparent; }
.hero-text p { color: var(--text-muted); font-size: 1.1rem; line-height: 1.6; max-width: 90%; }

.features-grid { display: flex; flex-direction: column; gap: 16px; margin-top: 40px; }
.feature-item { display: flex; align-items: center; gap: 12px; font-weight: 500; color: #cbd5e1; }
.f-icon { width: 32px; height: 32px; background: rgba(255,255,255,0.05); border-radius: 50%; display: grid; place-items: center; color: var(--accent); }

.footer-note p { color: rgba(255,255,255,0.3); font-size: 0.85rem; }

/* --- RIGHT PANEL --- */
.right-panel {
  flex: 1;
  padding: 40px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow-y: auto;
}

/* Tab Switcher */
.tab-switcher {
  position: relative;
  display: flex;
  background: rgba(0,0,0,0.2);
  padding: 4px;
  border-radius: 12px;
  margin-bottom: 30px;
  width: fit-content;
  align-self: flex-end; /* Align right */
}
.tab-bg {
  position: absolute;
  top: 4px; left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  background: var(--primary);
  border-radius: 10px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 0;
}
.tab-switcher button {
  flex: 1;
  border: none;
  background: none;
  padding: 10px 24px;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  position: relative;
  z-index: 1;
  transition: color 0.3s;
  min-width: 120px;
}
.tab-switcher button.active { color: white; }

/* Upload Zone */
.drop-zone {
  border: 2px dashed rgba(255,255,255,0.2);
  border-radius: 20px;
  height: 250px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(255,255,255,0.02);
  margin-bottom: 24px;
}
.drop-zone:hover { border-color: var(--primary); background: rgba(99, 102, 241, 0.05); }
.drop-zone.dragging { border-color: var(--accent); background: rgba(16, 185, 129, 0.1); transform: scale(1.02); }
.drop-zone.has-file { border-style: solid; border-color: var(--accent); }

.dz-content { text-align: center; }
.dz-icon-circle { width: 64px; height: 64px; background: rgba(99, 102, 241, 0.1); color: var(--primary); border-radius: 50%; display: grid; place-items: center; margin: 0 auto 16px; }
.dz-content h3 { font-size: 1.1rem; margin-bottom: 8px; }
.dz-content p { color: var(--text-muted); font-size: 0.9rem; }

.file-preview { display: flex; align-items: center; gap: 16px; width: 100%; padding: 0 40px; }
.file-icon { font-size: 3rem; }
.file-details { flex: 1; display: flex; flex-direction: column; }
.fn { font-weight: 600; font-size: 1.1rem; }
.fs { font-size: 0.9rem; color: var(--text-muted); }
.remove-file { background: rgba(255,255,255,0.1); border: none; width: 32px; height: 32px; border-radius: 50%; color: white; cursor: pointer; transition: 0.2s; }
.remove-file:hover { background: #ef4444; }

/* Settings */
.settings-box { margin-bottom: 24px; animation: slideUp 0.4s ease; }
.setting-row { margin-bottom: 20px; }
.setting-row label { display: block; font-size: 0.9rem; color: var(--text-muted); margin-bottom: 8px; }
.select-wrapper select {
  width: 100%;
  padding: 14px;
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border);
  border-radius: 12px;
  color: white;
  font-size: 1rem;
  outline: none;
  cursor: pointer;
}

/* Primary Button */
.primary-btn {
  width: 100%;
  padding: 16px;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  border: none;
  border-radius: 12px;
  color: white;
  font-weight: 600;
  font-size: 1.1rem;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 10px 20px -5px rgba(99, 102, 241, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.primary-btn:hover { transform: translateY(-2px); box-shadow: 0 15px 30px -5px rgba(99, 102, 241, 0.5); }
.primary-btn:disabled { background: #475569; cursor: not-allowed; transform: none; box-shadow: none; }

/* Spinner */
.spinner { width: 20px; height: 20px; border: 3px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Result Box */
.result-box { background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 20px; padding: 30px; text-align: center; animation: slideUp 0.4s ease; }
.result-header { color: var(--accent); display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 20px; }
.check-icon { width: 24px; height: 24px; background: var(--accent); color: #000; border-radius: 50%; font-weight: bold; display: grid; place-items: center; }

.link-box { display: flex; gap: 10px; margin-bottom: 20px; }
.link-box input { flex: 1; background: rgba(0,0,0,0.2); border: 1px solid var(--border); padding: 12px; border-radius: 10px; color: var(--accent); font-family: monospace; outline: none; }
.link-box button { background: var(--accent); color: #064e3b; border: none; padding: 0 20px; border-radius: 10px; font-weight: 600; cursor: pointer; }

.meta-actions { display: flex; justify-content: center; align-items: center; gap: 20px; margin-bottom: 20px; }
.id-pill { background: rgba(255,255,255,0.1); padding: 6px 12px; border-radius: 20px; font-size: 0.9rem; font-family: monospace; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.2s; }
.id-pill:hover { background: rgba(255,255,255,0.2); }
.qr-mini { border-radius: 8px; cursor: zoom-in; }
.reset-btn { background: none; border: none; color: var(--text-muted); text-decoration: underline; cursor: pointer; font-size: 0.9rem; }

/* Download View */
.download-card { margin-bottom: 40px; }
.download-card h2 { font-size: 2rem; margin-bottom: 10px; }
.input-group { display: flex; gap: 12px; margin: 24px 0; }
.input-group input { flex: 1; padding: 16px; border-radius: 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border); color: white; font-size: 1.1rem; outline: none; transition: border 0.3s; }
.input-group input:focus { border-color: var(--primary); }
.scan-trigger { width: 56px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 12px; color: white; cursor: pointer; transition: 0.2s; }
.scan-trigger:hover { background: rgba(255,255,255,0.1); }
.download-btn { background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 10px 20px -5px rgba(16, 185, 129, 0.4); }

/* History List */
.history-section h4 { color: var(--text-muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
.history-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.history-list li { display: flex; align-items: center; justify-content: space-between; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; transition: background 0.2s; }
.history-list li.clickable { cursor: pointer; }
.history-list li:hover { background: rgba(255,255,255,0.07); }
.h-left { display: flex; align-items: center; gap: 12px; overflow: hidden; }
.h-icon { width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center; font-size: 1.2rem; }
.h-icon.sent { background: rgba(99, 102, 241, 0.2); color: var(--primary); }
.h-icon.received { background: rgba(16, 185, 129, 0.2); color: var(--accent); }
.h-info { display: flex; flex-direction: column; overflow: hidden; }
.h-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.h-date { font-size: 0.8rem; color: var(--text-muted); }
.h-del, .clear-btn { background: none; border: none; color: #64748b; cursor: pointer; padding: 4px; transition: color 0.2s; }
.h-del:hover, .clear-btn:hover { color: #ef4444; }
.h-header { display: flex; justify-content: space-between; align-items: center; }

/* Utilities */
.error-banner { background: rgba(239, 68, 68, 0.1); color: #ef4444; padding: 12px; border-radius: 10px; margin-top: 16px; text-align: center; font-weight: 500; border: 1px solid rgba(239, 68, 68, 0.2); }

/* Transitions */
.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.3s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(20px); }
.fade-slide-leave-to { opacity: 0; transform: translateY(-20px); }
@keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* Scanner Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 100; display: grid; place-items: center; backdrop-filter: blur(5px); }
.scanner-card { background: #1e293b; padding: 24px; border-radius: 20px; width: 90%; max-width: 400px; text-align: center; border: 1px solid var(--border); }
.scanner-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.close-icon { background: none; border: none; font-size: 1.5rem; color: white; cursor: pointer; }
.qr-reader-box { width: 100%; border-radius: 12px; overflow: hidden; border: 2px solid var(--primary); }

/* Toast */
.toast { position: fixed; top: 30px; left: 50%; transform: translateX(-50%); background: var(--bg-card); border: 1px solid var(--primary); padding: 12px 24px; border-radius: 50px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 200; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.slide-fade-enter-active, .slide-fade-leave-active { transition: all 0.4s ease; }
.slide-fade-enter-from, .slide-fade-leave-to { transform: translate(-50%, -50px); opacity: 0; }

/* Responsive */
@media (max-width: 900px) {
  .glass-container { flex-direction: column; height: 100vh; width: 100%; border-radius: 0; border: none; overflow-y: scroll; }
  .left-panel { width: 100%; padding: 30px; min-height: 40vh; justify-content: center; text-align: center; }
  .brand { justify-content: center; margin-bottom: 20px; }
  .hero-text h1 { font-size: 2.5rem; }
  .features-grid { justify-content: center; flex-direction: row; flex-wrap: wrap; }
  .footer-note { display: none; }
  .right-panel { padding: 20px; overflow: visible; }
  .tab-switcher { width: 100%; align-self: center; }
  .orb-1 { width: 200px; height: 200px; }
  .orb-2 { width: 200px; height: 200px; }
}
</style>