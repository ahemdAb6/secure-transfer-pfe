<script setup>
import { ref, onMounted } from 'vue'
import { Html5Qrcode } from "html5-qrcode"

const props = defineProps(['session'])
const emit = defineEmits(['logout'])

// --- STATE ---
const currentTab = ref('upload')
const file = ref(null)
const loading = ref(false)
const result = ref(null)
const error = ref(null)

// Inputs
const fileIdInput = ref('')
const passwordInput = ref('')      
const downloadPassword = ref('')
const expirationTime = ref(86400)
const magicLink = ref('') 

// UI
const toast = ref({ show: false, message: '' })
const showScanner = ref(false)
const showPasswordModal = ref(false)
const currentDownloadId = ref(null)
const isDragging = ref(false) 
let html5QrCode = null

// History
const sentHistory = ref([])
const receivedHistory = ref([])

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

// --- UTILS ---
const switchTab = (tab) => { currentTab.value = tab; error.value = null; fileIdInput.value = ''; passwordInput.value = ''; }
const showToast = (msg) => { toast.value = { show: true, message: msg }; setTimeout(() => { toast.value.show = false }, 3000) }
const formatFileSize = (bytes) => { if (bytes < 1024) return bytes + ' B'; if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'; return (bytes / 1024 / 1024).toFixed(2) + ' MB' }
const extractId = (input) => { if (!input) return ""; if (input.includes('id=')) return input.split('id=')[1].split('&')[0]; return input.trim() }
const copyToClipboard = (text, msg) => { navigator.clipboard.writeText(text); showToast(msg) }

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

// --- DRAG & DROP ---
const onDragOver = (e) => { e.preventDefault(); isDragging.value = true }
const onDragLeave = () => { isDragging.value = false }
const onDrop = (e) => { e.preventDefault(); isDragging.value = false; if (e.dataTransfer.files.length > 0) { file.value = e.dataTransfer.files[0]; result.value = null; error.value = null } }
const handleFileChange = (e) => { file.value = e.target.files[0]; result.value = null; error.value = null }
const handleInputPaste = () => { setTimeout(() => { fileIdInput.value = extractId(fileIdInput.value) }, 100) }

// --- API ---
const uploadFile = async () => {
  if (!file.value) return showToast("⚠️ Select a file first")
  loading.value = true; result.value = null; error.value = null

  const formData = new FormData()
  formData.append("file", file.value)
  formData.append("expiration", expirationTime.value)
  formData.append("session_token", props.session.token)
  if (passwordInput.value) formData.append("password", passwordInput.value)

  try {
    const response = await fetch('/api/upload', { method: 'POST', body: formData })
    if (!response.ok) { 
      const errData = await response.json().catch(() => ({}))
      if (response.status === 401) { emit('logout'); throw new Error("Session Expired") }
      throw new Error(errData.detail || `Upload Failed (${response.status})`) 
    }
    const data = await response.json()
    result.value = data
    magicLink.value = `${window.location.origin}?id=${data.id}`
    addToSentHistory(data)
    passwordInput.value = ''
    showToast("✅ File Sent Successfully!")
  } catch (e) { result.value = null; error.value = e.message; showToast("❌ " + e.message) } finally { loading.value = false }
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
    if (response.status === 500) throw new Error("Server Error")
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
  } catch (e) { error.value = e.message; showToast("❌ " + e.message); if (e.message.includes("Password")) { showPasswordModal.value = true } } finally { loading.value = false }
}


</script>

<template>
  <div class="layout-container">
    
    <Transition name="toast-pop"><div v-if="toast.show" class="toast-wrapper"><div class="toast-pill"><span class="toast-dot"></span>{{ toast.message }}</div></div></Transition>

    <!-- LEFT SIDEBAR (Menu Only) -->
    <aside class="sidebar">
      <div class="brand">
        <div class="logo-box">⚡</div><span class="brand-text">Axelites</span>
      </div>

      <div class="menu-list">
        <div class="menu-label">Menu</div>
        <button class="menu-btn active"><span>📂</span> File Transfer</button>
        <button class="menu-btn"><span>⚙️</span> Settings</button>
      </div>
      
      <div class="sidebar-footer">
        <button @click="$emit('logout')" class="logout-btn">← Sign Out</button>
      </div>
    </aside>

    <!-- RIGHT PANEL (Content) -->
    <main class="main-content">
      
      <!-- HEADER WITH USER BADGE ON RIGHT -->
      <header class="top-bar">
        <div class="bar-left">
           <!-- Tabs moved here for better layout -->
           <nav class="nav-pills">
            <button :class="{ active: currentTab === 'upload' }" @click="switchTab('upload')">Send</button>
            <button :class="{ active: currentTab === 'download' }" @click="switchTab('download')">Receive</button>
           </nav>
        </div>

        <div class="bar-right">
          <div class="user-pill">
            <div class="user-avatar">{{ session?.email.charAt(0).toUpperCase() }}</div>
            <div class="user-text">
               <span class="u-email">{{ session?.email }}</span>
               <span class="verified-badge">Verified User <span class="dot"></span></span>
            </div>
          </div>
        </div>
      </header>

      <!-- CONTENT AREA -->
      <div class="content-body">
        
        <!-- UPLOAD VIEW -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'upload'" key="upload" class="workspace">
            <div class="dropzone" :class="{ 'dragging': isDragging, 'has-file': file }" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop" @click="!file && $refs.fileInput.click()">
              <input type="file" ref="fileInput" @change="handleFileChange" hidden>
              <div v-if="!file" class="dz-content">
                <div class="dz-icon">☁️</div><h3>Click or Drop File</h3><p>Secure Encryption • Max 5GB</p>
              </div>
              <div v-else class="file-card">
                <div class="f-icon">📄</div>
                <div class="f-info"><span class="name">{{ file.name }}</span><span class="size">{{ formatFileSize(file.size) }}</span></div>
                <button class="del-btn" @click.stop="file = null; result = null">✕</button>
              </div>
            </div>

            <div v-if="file && !result" class="controls">
              <div class="row">
                <select v-model="expirationTime" class="modern-input"><option :value="3600">Expire: 1 Hour</option><option :value="86400">Expire: 24 Hours</option><option :value="259200">Expire: 3 Days</option></select>
                <div class="password-wrap">
                  <input type="password" v-model="passwordInput" placeholder="Optional Password" class="modern-input">
                  <span class="eye-toggle" @click="$event.target.previousElementSibling.type = $event.target.previousElementSibling.type === 'password' ? 'text' : 'password'">👁️</span>
                </div>
              </div>
              <button class="action-btn" @click="uploadFile" :disabled="loading">{{ loading ? 'Encrypting...' : 'Transfer Securely' }}</button>
            </div>

            <div v-if="result" class="result-panel">
               <div class="success-msg">✓ Ready to Share</div>
               <div class="link-row"><input :value="magicLink" readonly><button @click="copyToClipboard(magicLink, 'Link Copied')">Copy</button></div>
               <button class="secondary-btn" @click="file = null; result = null">Send New File</button>
            </div>
            
            <div v-if="error" class="error-msg">{{ error }}</div>

            <!-- HISTORY -->
            <div v-if="sentHistory.length && !file && !result" class="history-list">
               <div class="list-head">Recent Transfers</div>
               <div v-for="(item, i) in sentHistory" :key="item.id" class="list-item">
                 <span class="i-icon">↑</span>
                 <div class="i-details"><span class="i-name">{{ item.name }}</span><span class="i-date">{{ item.date }}</span></div>
                 <button class="i-del" @click="deleteSentItem(i)">✕</button>
               </div>
            </div>
          </div>
        </Transition>

        <!-- DOWNLOAD VIEW -->
        <Transition name="fade-slide" mode="out-in">
          <div v-if="currentTab === 'download'" key="download" class="workspace centered">
             <div class="dl-box">
                <h2>Download File</h2>
                <div class="dl-input-row">
                   <input v-model="fileIdInput" @input="handleInputPaste" placeholder="Enter File ID or Link" class="modern-input lg">
                   
                </div>
                <button class="action-btn green" @click="() => initiateDownload()" :disabled="loading">{{ loading ? 'Searching...' : 'Download' }}</button>
                <div v-if="error" class="error-msg">{{ error }}</div>
             </div>
             
             <div v-if="receivedHistory.length" class="history-list">
               <div class="list-head">Received Files <button @click="clearReceivedHistory">Clear</button></div>
               <div v-for="(item, i) in receivedHistory" :key="item.id" class="list-item clickable" @click="initiateDownload(item.id)">
                 <span class="i-icon down">↓</span>
                 <div class="i-details"><span class="i-name">{{ item.name }}</span><span class="i-date">{{ item.date }}</span></div>
                 <button class="i-del" @click.stop="deleteReceivedItem(i)">✕</button>
               </div>
            </div>
          </div>
        </Transition>

      </div>
    </main>

    <!-- MODALS -->
    <div v-if="showPasswordModal" class="modal-bg"><div class="modal-box"><h3>🔒 Password Required</h3><input type="password" v-model="downloadPassword" class="modern-input" placeholder="Enter Password"><button class="action-btn" @click="confirmPassword">Unlock</button></div></div>
    <div v-if="showScanner" class="modal-bg"><div class="modal-box"><h3>Scan QR</h3><div id="reader"></div><button class="secondary-btn" @click="stopScanner">Close</button></div></div>

  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap');

/* LAYOUT */
.layout-container { display: flex; width: 100%; height: 100%; background: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; overflow: hidden; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); }

/* SIDEBAR */
.sidebar { width: 240px; background: rgba(30, 41, 59, 0.5); border-right: 1px solid rgba(255,255,255,0.05); padding: 24px; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 40px; }
.logo-box { width: 32px; height: 32px; background: #6366f1; border-radius: 8px; display: grid; place-items: center; }
.brand-text { font-weight: 700; font-size: 1.1rem; }
.menu-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; margin-bottom: 8px; font-weight: 600; }
.menu-btn { display: flex; gap: 10px; width: 100%; padding: 10px; background: none; border: none; color: #94a3b8; cursor: pointer; border-radius: 8px; font-weight: 500; transition: 0.2s; text-align: left; }
.menu-btn:hover { color: white; background: rgba(255,255,255,0.05); }
.menu-btn.active { color: #818cf8; background: rgba(99, 102, 241, 0.1); }
.logout-btn { margin-top: auto; background: none; border: 1px solid rgba(255,255,255,0.1); padding: 8px; color: #ef4444; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }
.logout-btn:hover { border-color: #ef4444; background: rgba(239, 68, 68, 0.1); }

/* MAIN CONTENT */
.main-content { flex: 1; display: flex; flex-direction: column; background: radial-gradient(circle at top right, rgba(99,102,241,0.1), transparent 50%); }

/* TOP BAR (Header) */
.top-bar { height: 70px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; }
.nav-pills { display: flex; background: rgba(0,0,0,0.3); padding: 4px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
.nav-pills button { background: none; border: none; padding: 6px 20px; color: #94a3b8; font-size: 0.9rem; font-weight: 500; cursor: pointer; border-radius: 6px; transition: 0.2s; }
.nav-pills button.active { background: #6366f1; color: white; font-weight: 600; }

/* USER PILL (Top Right Badge) */
.user-pill { display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.03); padding: 6px 12px 6px 6px; border-radius: 30px; border: 1px solid rgba(255,255,255,0.05); }
.user-avatar { width: 32px; height: 32px; background: #6366f1; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 0.9rem; }
.user-text { display: flex; flex-direction: column; line-height: 1.1; }
.u-email { font-size: 0.8rem; font-weight: 500; color: white; }
.verified-badge { font-size: 0.65rem; color: #10b981; font-weight: 700; text-transform: uppercase; display: flex; align-items: center; gap: 4px; }
.dot { width: 6px; height: 6px; background: #10b981; border-radius: 50%; box-shadow: 0 0 5px #10b981; animation: pulse 2s infinite; }
@keyframes pulse { 0% { opacity: 0.5; } 50% { opacity: 1; } 100% { opacity: 0.5; } }

/* BODY */
.content-body { flex: 1; padding: 32px; overflow-y: auto; display: flex; justify-content: center; }
.workspace { width: 100%; max-width: 500px; display: flex; flex-direction: column; gap: 20px; }
.centered { align-items: center; }

/* DROPZONE */
.dropzone { height: 200px; border: 1px dashed rgba(255,255,255,0.2); border-radius: 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; background: rgba(255,255,255,0.01); transition: 0.2s; }
.dropzone:hover, .dropzone.dragging { border-color: #6366f1; background: rgba(99, 102, 241, 0.05); }
.dz-icon { font-size: 2rem; margin-bottom: 10px; opacity: 0.7; }
.dz-content h3 { font-size: 1rem; margin-bottom: 4px; }
.dz-content p { color: #64748b; font-size: 0.8rem; }
.file-card { display: flex; align-items: center; gap: 12px; padding: 10px 20px; background: #1e293b; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); }
.f-icon { font-size: 1.5rem; }
.f-info { display: flex; flex-direction: column; }
.name { font-weight: 500; font-size: 0.9rem; }
.size { color: #64748b; font-size: 0.75rem; }
.del-btn { background: none; border: none; color: #64748b; cursor: pointer; font-size: 1.2rem; }

/* CONTROLS */
.row { display: flex; gap: 10px; margin-bottom: 15px; }
.modern-input { flex: 1; background: #1e293b; border: 1px solid rgba(255,255,255,0.1); padding: 12px; border-radius: 10px; color: white; outline: none; width: 100%; }
.modern-input:focus { border-color: #6366f1; }
.password-wrap { position: relative; flex: 1; display: flex; }
.eye-toggle { position: absolute; right: 10px; top: 12px; cursor: pointer; opacity: 0.6; font-size: 1rem; }
.action-btn { width: 100%; padding: 14px; border: none; border-radius: 10px; font-weight: 600; cursor: pointer; font-size: 1rem; background: linear-gradient(180deg, #6366f1, #4f46e5); color: white; transition: 0.2s; }
.action-btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
.action-btn.green { background: linear-gradient(180deg, #10b981, #059669); }
.action-btn:disabled { opacity: 0.7; cursor: not-allowed; }

/* RESULT */
.result-panel { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); padding: 20px; border-radius: 12px; text-align: center; }
.success-msg { color: #10b981; font-weight: 600; margin-bottom: 10px; }
.link-row { display: flex; gap: 8px; margin-bottom: 10px; }
.link-row input { flex: 1; background: #0f172a; border: 1px solid rgba(16,185,129,0.3); color: #10b981; padding: 8px; border-radius: 6px; font-family: monospace; }
.link-row button { background: #10b981; border: none; color: #064e3b; padding: 0 12px; border-radius: 6px; font-weight: 600; cursor: pointer; }
.secondary-btn { background: none; border: none; text-decoration: underline; color: #94a3b8; cursor: pointer; margin-top: 10px; font-size: 0.85rem; }

/* HISTORY */
.history-list { margin-top: 30px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px; width: 100%; }
.list-head { color: #64748b; font-size: 0.8rem; text-transform: uppercase; font-weight: 700; margin-bottom: 10px; display: flex; justify-content: space-between; }
.list-item { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 8px; background: rgba(255,255,255,0.03); margin-bottom: 8px; }
.list-item.clickable { cursor: pointer; }
.list-item.clickable:hover { background: rgba(255,255,255,0.06); }
.i-icon { width: 28px; height: 28px; background: rgba(99, 102, 241, 0.15); color: #818cf8; border-radius: 6px; display: grid; place-items: center; font-size: 0.9rem; }
.i-icon.down { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.i-details { flex: 1; display: flex; flex-direction: column; }
.i-name { font-size: 0.9rem; font-weight: 500; }
.i-date { font-size: 0.75rem; color: #64748b; }
.i-del { background: none; border: none; color: #64748b; cursor: pointer; padding: 4px; }
.i-del:hover { color: #ef4444; }

/* DOWNLOAD BOX */
.dl-box { width: 100%; text-align: center; margin-bottom: 30px; }
.dl-box h2 { margin-bottom: 20px; }
.dl-input-row { display: flex; gap: 8px; margin-bottom: 15px; }
.lg { font-size: 1.1rem; }
.scan-btn { width: 50px; border-radius: 10px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: white; cursor: pointer; font-size: 1.2rem; }

/* HELPERS */
.error-msg { background: rgba(239, 68, 68, 0.15); color: #ef4444; padding: 10px; border-radius: 8px; margin-top: 15px; text-align: center; }
.toast-wrapper { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 100; }
.toast-pill { background: #1e293b; padding: 10px 20px; border-radius: 50px; border: 1px solid #6366f1; display: flex; gap: 10px; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
.toast-dot { width: 8px; height: 8px; background: #6366f1; border-radius: 50%; box-shadow: 0 0 5px #6366f1; }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 99; display: grid; place-items: center; }
.modal-box { background: #1e293b; padding: 30px; border-radius: 20px; width: 90%; max-width: 400px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
#reader { width: 100%; height: 250px; background: black; margin-bottom: 10px; border-radius: 8px; }

/* MEDIA */
@media (max-width: 900px) {
  .layout-container { flex-direction: column; border-radius: 0; height: 100vh; overflow-y: scroll; }
  .sidebar { width: 100%; padding: 16px; flex-direction: row; align-items: center; justify-content: space-between; }
  .menu-list, .brand-text { display: none; }
  .logout-btn { margin: 0; }
  .top-bar { padding: 0 16px; }
  .content-body { padding: 16px; }
}
</style>