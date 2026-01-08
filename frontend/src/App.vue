<script setup>
import { ref, onMounted } from 'vue'
import { Html5Qrcode } from "html5-qrcode"

// --- APP STATE ---
const currentView = ref('home') // 'home', 'admin-login', 'admin-dashboard'
const currentTab = ref('upload')
const file = ref(null)
const loading = ref(false)
const result = ref(null)
const error = ref(null)

// --- INPUTS ---
const fileIdInput = ref('')
const passwordInput = ref('')      
const senderEmail = ref('')        
const downloadPassword = ref('')
const adminKeyInput = ref('')      // Input for Admin Login

const expirationTime = ref(86400)
const magicLink = ref('') 
const toast = ref({ show: false, message: '' })
const showScanner = ref(false)
const showPasswordModal = ref(false)
const currentDownloadId = ref(null)
const sentHistory = ref([])
const receivedHistory = ref([])
const isDragging = ref(false) 
let html5QrCode = null

// --- ADMIN DATA ---
const adminData = ref(null)

// --- LIFECYCLE ---
onMounted(() => {
  const savedSent = localStorage.getItem('sentHistory')
  const savedReceived = localStorage.getItem('receivedHistory')
  if (savedSent) sentHistory.value = JSON.parse(savedSent)
  if (savedReceived) receivedHistory.value = JSON.parse(savedReceived)

  const urlParams = new URLSearchParams(window.location.search)
  const idFromUrl = urlParams.get('id')
  if (idFromUrl) {
    currentTab.value = 'download'
    fileIdInput.value = idFromUrl
    window.history.replaceState({}, document.title, window.location.pathname)
  }
})

// --- NAVIGATION ---
const goToAdmin = () => { currentView.value = 'admin-login'; error.value = null }
const goToHome = () => { currentView.value = 'home'; adminKeyInput.value = ''; error.value = null }

// --- UTILS ---
const switchTab = (tab) => { currentTab.value = tab; error.value = null; fileIdInput.value = ''; passwordInput.value = ''; senderEmail.value = '' }
const showToast = (msg) => { toast.value = { show: true, message: msg }; setTimeout(() => { toast.value.show = false }, 3000) }
const formatFileSize = (bytes) => { if (bytes < 1024) return bytes + ' B'; if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'; return (bytes / 1024 / 1024).toFixed(2) + ' MB' }
const extractId = (input) => { if (!input) return ""; if (input.includes('id=')) return input.split('id=')[1].split('&')[0]; return input.trim() }
const copyToClipboard = (text, msg) => { navigator.clipboard.writeText(text); showToast(msg) }

// --- ADMIN LOGIC ---
const loginAdmin = async () => {
  if (!adminKeyInput.value) return
  loading.value = true
  try {
    const response = await fetch(`/api/admin/dashboard?key=${adminKeyInput.value}`)
    if (!response.ok) throw new Error("Invalid Key")
    const data = await response.json()
    adminData.value = data
    currentView.value = 'admin-dashboard' // Switch to Dashboard View
  } catch (e) {
    showToast("❌ Access Denied: Wrong Key")
  } finally {
    loading.value = false
  }
}

const deleteFileAsAdmin = async (fileId) => {
  if(!confirm("⚠️ Force delete this file? This cannot be undone.")) return
  try {
    const res = await fetch(`/api/admin/delete/${fileId}?key=${adminKeyInput.value}`, { method: 'DELETE' })
    if(res.ok) {
      showToast("✅ File Deleted")
      // Refresh Data
      const response = await fetch(`/api/admin/dashboard?key=${adminKeyInput.value}`)
      adminData.value = await response.json()
    }
  } catch(e) { showToast("❌ Error deleting file") }
}

// --- HISTORY LOGIC ---
const addToSentHistory = (data) => {
  const newItem = { id: data.id, name: data.filename, date: new Date().toLocaleDateString(), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), size: file.value ? formatFileSize(file.value.size) : '?' }
  sentHistory.value.unshift(newItem); if (sentHistory.value.length > 20) sentHistory.value.pop(); localStorage.setItem('sentHistory', JSON.stringify(sentHistory.value))
}
const addToReceivedHistory = (id, filename) => {
  if (receivedHistory.value.some(item => item.id === id)) return
  const newItem = { id: id, name: filename, date: new Date().toLocaleDateString(), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  receivedHistory.value.unshift(newItem); if (receivedHistory.value.length > 20) receivedHistory.value.pop(); localStorage.setItem('receivedHistory', JSON.stringify(receivedHistory.value))
}
const deleteSentItem = (index) => { sentHistory.value.splice(index, 1); localStorage.setItem('sentHistory', JSON.stringify(sentHistory.value)) }
const deleteReceivedItem = (index) => { receivedHistory.value.splice(index, 1); localStorage.setItem('receivedHistory', JSON.stringify(receivedHistory.value)) }
const clearReceivedHistory = () => { receivedHistory.value = []; localStorage.removeItem('receivedHistory') }

// --- FILE HANDLERS ---
const onDragOver = (e) => { e.preventDefault(); isDragging.value = true }
const onDragLeave = () => { isDragging.value = false }
const onDrop = (e) => { e.preventDefault(); isDragging.value = false; if (e.dataTransfer.files.length > 0) { file.value = e.dataTransfer.files[0]; result.value = null; error.value = null } }
const handleFileChange = (e) => { file.value = e.target.files[0]; result.value = null; error.value = null }
const handleInputPaste = () => { setTimeout(() => { fileIdInput.value = extractId(fileIdInput.value) }, 100) }

// --- API ACTIONS ---
// --- API: UPLOAD (SENDER) ---
const uploadFile = async () => {
  // 1. Validation: File
  if (!file.value) return showToast("⚠️ Select a file first")
  
  // 2. Validation: Email (OBLIGATORY NOW)
  if (!senderEmail.value || !senderEmail.value.includes('@')) {
    return showToast("⚠️ Sender Email is required!")
  }

  loading.value = true; result.value = null; error.value = null

  const formData = new FormData()
  formData.append("file", file.value)
  formData.append("expiration", expirationTime.value)
  formData.append("sender_email", senderEmail.value) // Always send it
  
  if (passwordInput.value) {
    formData.append("password", passwordInput.value)
  }

  try {
    const response = await fetch('/api/upload', { method: 'POST', body: formData })
    if (!response.ok) { 
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || `Upload Failed (${response.status})`) 
    }
    const data = await response.json()
    
    result.value = data
    magicLink.value = `${window.location.origin}?id=${data.id}`
    addToSentHistory(data)
    
    // Clear inputs
    passwordInput.value = ''
    // We KEEP senderEmail.value so they don't have to re-type it for the next file
    
    showToast("✅ File Sent Successfully!")
  } catch (e) { 
    result.value = null; 
    error.value = e.message; 
    showToast("❌ " + e.message) 
  } finally { 
    loading.value = false 
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
    if (meta.protected) { currentDownloadId.value = id; showPasswordModal.value = true; downloadPassword.value = ''; loading.value = false; return } 
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
    if (response.status === 500) throw new Error("Server Error: Decryption failed")
    if (!response.ok) throw new Error("Download failed")
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const disposition = response.headers.get('Content-Disposition')
    let fileName = 'file'
    if (disposition && disposition.match(/filename="?(.+)"?/)) fileName = disposition.match(/filename="?(.+)"?/)[1]
    a.download = fileName.replace(/"/g, ''); document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url)
    addToReceivedHistory(id, fileName); fileIdInput.value = ''; currentDownloadId.value = null; downloadPassword.value = ''
    showToast("⬇️ Download started...")
  } catch (e) { error.value = e.message; showToast("❌ " + e.message); if (e.message.includes("Password")) { showPasswordModal.value = true } } 
  finally { loading.value = false }
}

const startScanner = () => {
  showScanner.value = true; error.value = null
  setTimeout(() => {
    if (html5QrCode) { try { html5QrCode.stop(); html5QrCode.clear() } catch(e){} }
    html5QrCode = new Html5Qrcode("reader")
    html5QrCode.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 250, height: 250 } }, 
      (decodedText) => { stopScanner(); const cleanID = extractId(decodedText); fileIdInput.value = cleanID; initiateDownload(cleanID) },
      (err) => {}
    ).catch(err => { showScanner.value = false; showToast("❌ Camera Error") })
  }, 300)
}
const stopScanner = () => { if (html5QrCode) { html5QrCode.stop().then(() => { html5QrCode.clear(); showScanner.value = false }).catch(() => { showScanner.value = false }) } else { showScanner.value = false } }
</script>

<template>
  <div class="main-layout">
    <!-- Animated Background -->
    <div class="ambient-bg"></div>
    <div class="ambient-orb orb-1"></div>
    <div class="ambient-orb orb-2"></div>

    <!-- Notifications -->
    <Transition name="slide-fade"><div v-if="toast.show" class="toast">{{ toast.message }}</div></Transition>

    <!-- === VIEW 1: HOME (Send/Receive) === -->
    <div v-if="currentView === 'home'" class="glass-container">
      <aside class="left-panel">
        <div class="brand"><div class="logo-box">⚡</div><span class="brand-name">SecureTransfer</span></div>
        <div class="hero-text"><h1>Transfer files<br><span class="text-gradient">Securely.</span></h1><p>End-to-end encryption. No logs. Self-hosted.</p></div>
        <div class="features-grid">
          <div class="feature-item"><span class="f-icon">🔒</span><span>AES-256</span></div>
          <div class="feature-item"><span class="f-icon">⚡</span><span>Fast CDN</span></div>
          <div class="feature-item"><span class="f-icon">🔑</span><span>Password Protection</span></div>
        </div>
        <div class="footer-note">
          <!-- PROFESSIONAL ADMIN LINK -->
          <a href="#" @click.prevent="goToAdmin" class="admin-link">Admin Portal</a>
          <span>&copy; 2024 SecureTransfer Inc.</span>
        </div>
      </aside>

      <main class="right-panel">
        <nav class="tab-switcher">
          <div class="tab-bg" :style="{ transform: currentTab === 'upload' ? 'translateX(0)' : 'translateX(100%)' }"></div>
          <button :class="{ active: currentTab === 'upload' }" @click="switchTab('upload')">Send File</button>
          <button :class="{ active: currentTab === 'download' }" @click="switchTab('download')">Receive File</button>
        </nav>

        <!-- UPLOAD CONTENT -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'upload'" key="upload" class="panel-content">
            <div class="drop-zone" :class="{ 'dragging': isDragging, 'has-file': file }" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop" @click="!file && $refs.fileInput.click()">
              <input type="file" ref="fileInput" @change="handleFileChange" hidden>
              <div v-if="!file" class="dz-content"><div class="dz-icon-circle">📁</div><h3>Drop file here</h3><p>Max 5GB</p></div>
              <div v-else class="file-preview"><div class="file-icon">📄</div><div class="file-details"><span class="fn">{{ file.name }}</span><span class="fs">{{ formatFileSize(file.size) }}</span></div><button class="remove-file" @click.stop="file = null; result = null">✕</button></div>
            </div>
            <div v-if="file && !result" class="settings-box">
              <div class="setting-row"><label>Auto-Destruct</label><div class="select-wrapper"><select v-model="expirationTime"><option :value="3600">1 Hour</option><option :value="86400">24 Hours</option><option :value="259200">3 Days</option></select></div></div>
              <div class="setting-row"><label>Sender Email </label><input type="email" v-model="senderEmail" placeholder="To identify sender..." class="password-input-main" required></div>
              <div class="setting-row"><label>Password (Optional)</label><input type="password" v-model="passwordInput" maxlength="50" placeholder="Protection..." class="password-input-main"></div>
              <button class="primary-btn" @click="uploadFile" :disabled="loading"><span v-if="loading" class="spinner"></span>{{ loading ? 'Encrypting...' : 'Secure Transfer' }}</button>
            </div>
            <div v-if="result" class="result-box">
              <div class="result-header"><div class="check-icon">✓</div><h3>File Sent!</h3></div>
              <div class="link-box"><input type="text" readonly :value="magicLink"><button @click="copyToClipboard(magicLink, 'Link Copied!')">Copy</button></div>
              <div class="meta-actions">
                 <div class="id-pill" @click="copyToClipboard(result.id, 'ID Copied!')">ID: {{ result.id }}</div>
                 <div class="qr-trigger"><img :src="`https://api.qrserver.com/v1/create-qr-code/?size=150x150&color=6366f1&bgcolor=eef2ff&data=${encodeURIComponent(magicLink)}`" alt="QR" class="qr-mini" /></div>
              </div>
              <button class="reset-btn" @click="file = null; result = null">Send Another</button>
            </div>
            <div v-if="error" class="error-banner"><span>⚠️ {{ error }}</span></div>
            <div v-if="sentHistory.length > 0 && !file && !result" class="history-section"><h4>Recent Uploads</h4><ul class="history-list"><li v-for="(item, index) in sentHistory" :key="item.id"><div class="h-left"><div class="h-icon sent">↑</div><div class="h-info"><span class="h-name">{{ item.name }}</span><span class="h-date">{{ item.date }}</span></div></div><button class="h-del" @click="deleteSentItem(index)">✕</button></li></ul></div>
          </div>
        </Transition>

        <!-- DOWNLOAD CONTENT -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'download'" key="download" class="panel-content">
            <div class="download-card">
              <h2>Receive File</h2>
              <div class="input-group"><input v-model="fileIdInput" @input="handleInputPaste" type="text" placeholder="Paste ID or Link..."><button class="scan-trigger" @click="startScanner">📷</button></div>
              <button class="primary-btn download-btn" @click="() => initiateDownload()" :disabled="loading"><span v-if="loading" class="spinner"></span>{{ loading ? 'Checking...' : 'Download' }}</button>
              <div v-if="error" class="error-banner"><span>⚠️ {{ error }}</span></div>
            </div>
            <div v-if="receivedHistory.length > 0" class="history-section"><div class="h-header"><h4>Received Files</h4><button class="clear-btn" @click="clearReceivedHistory">Clear All</button></div><ul class="history-list"><li v-for="(item, index) in receivedHistory" :key="item.id" @click="initiateDownload(item.id)" class="clickable"><div class="h-left"><div class="h-icon received">↓</div><div class="h-info"><span class="h-name">{{ item.name }}</span><span class="h-date">{{ item.date }}</span></div></div><button class="h-del" @click.stop="deleteReceivedItem(index)">✕</button></li></ul></div>
          </div>
        </Transition>
      </main>
    </div>

    <!-- === VIEW 2: ADMIN LOGIN (Full Screen) === -->
    <div v-else-if="currentView === 'admin-login'" class="glass-container admin-login-container">
      <div class="admin-login-card">
        <div class="admin-icon">🛡️</div>
        <h2>Admin Portal</h2>
        <p>Restricted access for Axelites Administrators.</p>
        
        <input 
          type="password" 
          v-model="adminKeyInput" 
          placeholder="Enter Master Key" 
          class="password-input-main"
          @keyup.enter="loginAdmin"
        >
        
        <button class="primary-btn" @click="loginAdmin" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? 'Verifying...' : 'Access Dashboard' }}
        </button>
        
        <button class="reset-btn" @click="goToHome">← Back to Home</button>
      </div>
    </div>

    <!-- === VIEW 3: ADMIN DASHBOARD (Full Screen) === -->
    <div v-else-if="currentView === 'admin-dashboard'" class="glass-container admin-dashboard-container">
      <div class="dashboard-header">
        <div class="brand"><div class="logo-box" style="background:#10b981">🛡️</div><span class="brand-name">Admin Dashboard</span></div>
        <button class="reset-btn" @click="goToHome">Logout</button>
      </div>

      <div class="dashboard-stats">
        <div class="stat-card">
          <h3>Active Files</h3>
          <div class="stat-value">{{ adminData?.total_active_files || 0 }}</div>
        </div>
        <div class="stat-card">
          <h3>System Status</h3>
          <div class="stat-value" style="color:#10b981">Online</div>
        </div>
      </div>

      <div class="dashboard-content">
        <h3>File Management</h3>
        <table class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Filename</th>
              <th>Sender</th>
              <th>Protected</th>
              <th>Downloads</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in adminData?.files" :key="f.id">
              <td class="mono-font">{{ f.id.substring(0,8) }}...</td>
              <td>{{ f.filename }}</td>
              <td>{{ f.sender }}</td>
              <td>{{ f.protected }}</td>
              <td>{{ f.downloads }}</td>
              <td><button class="delete-btn" @click="deleteFileAsAdmin(f.id)">DELETE</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!adminData?.files.length" class="empty-state-admin">No active transfers found.</div>
      </div>
    </div>

    <!-- MODALS -->
    <Transition name="fade"><div v-if="showPasswordModal" class="modal-overlay"><div class="scanner-card"><div class="scanner-header"><h3>🔒 Password Required</h3><button @click="showPasswordModal = false" class="close-icon">✕</button></div><input type="password" v-model="downloadPassword" class="password-input-modal"><button class="primary-btn" @click="confirmPassword" style="margin-top:10px">Unlock</button></div></div></Transition>
    <Transition name="fade"><div v-if="showScanner" class="modal-overlay"><div class="scanner-card"><div class="scanner-header"><h3>Scan QR</h3><button @click="stopScanner" class="close-icon">✕</button></div><div id="reader" class="qr-reader-box"></div></div></div></Transition>

  </div>
</template>

<style scoped>
/* Keeping previous styles, adding specific Admin Styles */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
:root { --primary: #6366f1; --primary-dark: #4f46e5; --accent: #10b981; --bg-dark: #0f172a; --bg-card: #1e293b; --text-main: #f8fafc; --text-muted: #94a3b8; --border: rgba(255,255,255,0.1); }
.main-layout { position: relative; width: 100vw; height: 100vh; background-color: var(--bg-dark); color: var(--text-main); display: flex; justify-content: center; align-items: center; overflow: hidden; }
.ambient-bg { position: absolute; inset: 0; background: radial-gradient(circle at 15% 50%, #1e1b4b 0%, #0f172a 50%, #020617 100%); z-index: 0; }
.ambient-orb { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; animation: float 20s infinite ease-in-out; }
.orb-1 { width: 400px; height: 400px; background: #4f46e5; top: -100px; left: -100px; }
.orb-2 { width: 500px; height: 500px; background: #0ea5e9; bottom: -150px; right: -150px; animation-delay: -5s; }
.glass-container { position: relative; z-index: 10; display: flex; width: 90%; max-width: 1200px; height: 85vh; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(20px); border-radius: 24px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); overflow: hidden; }
.left-panel { width: 40%; background: rgba(0, 0, 0, 0.2); padding: 60px; display: flex; flex-direction: column; justify-content: space-between; border-right: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 12px; }
.logo-box { width: 40px; height: 40px; background: var(--primary); border-radius: 10px; display: grid; place-items: center; font-size: 20px; }
.brand-name { font-weight: 700; font-size: 1.5rem; }
.hero-text h1 { font-size: 3.5rem; line-height: 1.1; font-weight: 800; margin-bottom: 20px; }
.text-gradient { background: linear-gradient(to right, #818cf8, #2dd4bf); -webkit-background-clip: text; color: transparent; }
.hero-text p { color: var(--text-muted); font-size: 1.1rem; line-height: 1.6; }
.features-grid { display: flex; flex-direction: column; gap: 16px; margin-top: 40px; }
.feature-item { display: flex; align-items: center; gap: 12px; font-weight: 500; color: #cbd5e1; }
.f-icon { width: 32px; height: 32px; background: rgba(255,255,255,0.05); border-radius: 50%; display: grid; place-items: center; color: var(--accent); }
.footer-note { display: flex; gap: 15px; font-size: 0.85rem; color: var(--text-muted); }
.admin-link { color: var(--text-muted); text-decoration: none; border-bottom: 1px dotted var(--text-muted); transition: 0.3s; }
.admin-link:hover { color: var(--accent); border-color: var(--accent); }
.right-panel { flex: 1; padding: 40px; display: flex; flex-direction: column; position: relative; overflow-y: auto; }
.tab-switcher { position: relative; display: flex; background: rgba(0,0,0,0.2); padding: 4px; border-radius: 12px; margin-bottom: 30px; width: fit-content; align-self: flex-end; }
.tab-bg { position: absolute; top: 4px; left: 4px; width: calc(50% - 4px); height: calc(100% - 8px); background: var(--primary); border-radius: 10px; transition: transform 0.3s; z-index: 0; }
.tab-switcher button { flex: 1; border: none; background: none; padding: 10px 24px; color: var(--text-muted); font-weight: 600; cursor: pointer; position: relative; z-index: 1; min-width: 120px; }
.tab-switcher button.active { color: white; }
.drop-zone { border: 2px dashed rgba(255,255,255,0.2); border-radius: 20px; height: 250px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: 0.3s; background: rgba(255,255,255,0.02); margin-bottom: 24px; }
.drop-zone:hover { border-color: var(--primary); background: rgba(99, 102, 241, 0.05); }
.dz-icon-circle { width: 64px; height: 64px; background: rgba(99, 102, 241, 0.1); color: var(--primary); border-radius: 50%; display: grid; place-items: center; margin-bottom: 16px; font-size: 24px; }
.file-preview { display: flex; align-items: center; gap: 16px; width: 100%; padding: 0 40px; }
.file-icon { font-size: 3rem; }
.file-details { flex: 1; display: flex; flex-direction: column; }
.fn { font-weight: 600; font-size: 1.1rem; }
.remove-file { background: rgba(255,255,255,0.1); border: none; width: 32px; height: 32px; border-radius: 50%; color: white; cursor: pointer; }
.settings-box { margin-bottom: 24px; animation: slideUp 0.4s ease; }
.setting-row { margin-bottom: 20px; }
.setting-row label { display: block; font-size: 0.9rem; color: var(--text-muted); margin-bottom: 8px; }
.select-wrapper select, .password-input-main { width: 100%; padding: 14px; background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: 12px; color: white; font-size: 1rem; outline: none; }
.primary-btn { width: 100%; padding: 16px; background: linear-gradient(135deg, var(--primary), var(--primary-dark)); border: none; border-radius: 12px; color: white; font-weight: 600; font-size: 1.1rem; cursor: pointer; transition: 0.3s; display: flex; align-items: center; justify-content: center; gap: 10px; }
.primary-btn:hover { transform: translateY(-2px); box-shadow: 0 15px 30px -5px rgba(99, 102, 241, 0.5); }
.result-box { background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 20px; padding: 30px; text-align: center; animation: slideUp 0.4s ease; }
.result-header { color: var(--accent); display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 20px; }
.check-icon { width: 24px; height: 24px; background: var(--accent); color: #000; border-radius: 50%; font-weight: bold; display: grid; place-items: center; }
.link-box { display: flex; gap: 10px; margin-bottom: 20px; }
.link-box input { flex: 1; background: rgba(0,0,0,0.2); border: 1px solid var(--border); padding: 12px; border-radius: 10px; color: var(--accent); font-family: monospace; outline: none; }
.link-box button { background: var(--accent); color: #064e3b; border: none; padding: 0 20px; border-radius: 10px; font-weight: 600; cursor: pointer; }
.meta-actions { display: flex; justify-content: center; align-items: center; gap: 20px; margin-bottom: 20px; }
.id-pill { background: rgba(255,255,255,0.1); padding: 6px 12px; border-radius: 20px; font-size: 0.9rem; font-family: monospace; cursor: pointer; }
.qr-mini { border-radius: 8px; cursor: zoom-in; }
.reset-btn { background: none; border: none; color: var(--text-muted); text-decoration: underline; cursor: pointer; font-size: 0.9rem; }
.download-card h2 { font-size: 2rem; margin-bottom: 10px; }
.input-group { display: flex; gap: 12px; margin: 24px 0; }
.input-group input { flex: 1; padding: 16px; border-radius: 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border); color: white; font-size: 1.1rem; outline: none; }
.scan-trigger { width: 56px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 12px; color: white; cursor: pointer; font-size: 24px; }
.download-btn { background: linear-gradient(135deg, #10b981, #059669); }
.history-section h4 { color: var(--text-muted); font-size: 0.8rem; text-transform: uppercase; margin-bottom: 12px; }
.history-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.history-list li { display: flex; align-items: center; justify-content: space-between; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; }
.h-icon { width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center; font-size: 1.2rem; }
.h-icon.sent { background: rgba(99, 102, 241, 0.2); color: var(--primary); }
.h-icon.received { background: rgba(16, 185, 129, 0.2); color: var(--accent); }
.error-banner { background: rgba(239, 68, 68, 0.1); color: #ef4444; padding: 12px; border-radius: 10px; margin-top: 16px; text-align: center; font-weight: 500; border: 1px solid rgba(239, 68, 68, 0.2); }
.toast { position: fixed; top: 30px; left: 50%; transform: translateX(-50%); background: var(--bg-card); border: 1px solid var(--primary); padding: 12px 24px; border-radius: 50px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 200; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.slide-fade-enter-active, .slide-fade-leave-active, .fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.3s ease; }
.slide-fade-enter-from { opacity: 0; transform: translate(-50%, -50px); }
.fade-slide-enter-from { opacity: 0; transform: translateY(20px); } .fade-slide-leave-to { opacity: 0; transform: translateY(-20px); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 100; display: grid; place-items: center; backdrop-filter: blur(5px); }
.scanner-card { background: #1e293b; padding: 24px; border-radius: 20px; width: 90%; max-width: 400px; text-align: center; border: 1px solid var(--border); }
.password-input-modal { width: 100%; padding: 14px; background: rgba(0,0,0,0.3); border: 2px solid var(--primary); border-radius: 10px; color: white; font-size: 1.1rem; text-align: center; outline: none; margin-top: 15px; }

/* --- ADMIN VIEW STYLES --- */
.admin-login-container { display: flex; justify-content: center; align-items: center; }
.admin-login-card { width: 100%; max-width: 400px; text-align: center; }
.admin-icon { font-size: 4rem; margin-bottom: 20px; }
.admin-dashboard-container { flex-direction: column; padding: 40px; }
.dashboard-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
.dashboard-stats { display: flex; gap: 20px; margin-bottom: 30px; }
.stat-card { background: rgba(255,255,255,0.05); padding: 20px; border-radius: 16px; min-width: 150px; }
.stat-value { font-size: 2rem; font-weight: 700; margin-top: 10px; }
.admin-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.admin-table th, .admin-table td { padding: 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
.admin-table th { color: var(--text-muted); font-size: 0.9rem; }
.mono-font { font-family: monospace; opacity: 0.7; }
.delete-btn { background: #ef4444; color: white; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: 600; }
.delete-btn:hover { background: #dc2626; }
.empty-state-admin { text-align: center; padding: 40px; color: var(--text-muted); border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px; margin-top: 10px; }

@media (max-width: 900px) { .glass-container { flex-direction: column; height: 100vh; width: 100%; border-radius: 0; border: none; overflow-y: scroll; } .left-panel { width: 100%; padding: 30px; min-height: 40vh; justify-content: center; text-align: center; } .right-panel { padding: 20px; overflow: visible; } .tab-switcher { width: 100%; align-self: center; } }
</style>