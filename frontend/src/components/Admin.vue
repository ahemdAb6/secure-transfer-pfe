<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps(['apiKey']) // Receives key from App.vue
const emit = defineEmits(['logout'])

const activeTab = ref('users') 
const loading = ref(false)
const data = ref({ users: [], files: [] })
const error = ref(null)

const loadDashboard = async () => {
  loading.value = true
  try {
    const res = await fetch(`/api/admin/dashboard?key=${props.apiKey}`)
    if(!res.ok) throw new Error("Connection Failed")
    data.value = await res.json()
  } catch(e) { error.value = "Failed to load data" }
  finally { loading.value = false }
}

onMounted(() => { loadDashboard() })

const updateUserStatus = async (email, action) => {
  if (action === 'BAN' && !confirm(`Ban ${email}?`)) return
  await fetch('/api/admin/user_action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ key: props.apiKey, email, action })
  })
  loadDashboard()
}

const deleteUser = async (email) => {
  if(!confirm(`⚠️ DELETE USER ${email}?\nThis cannot be undone.`)) return
  await fetch(`/api/admin/delete_user/${email}?key=${props.apiKey}`, { method: 'DELETE' })
  loadDashboard()
}

const updateUserLimit = async (email) => {
  const newLimit = prompt("Set Daily Upload Limit (Files per day):", "50")
  if (!newLimit || isNaN(newLimit)) return
  
  await fetch('/api/admin/user_limit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ key: props.apiKey, email, limit: parseInt(newLimit) })
  })
  loadDashboard()
}

const deleteFile = async (id) => {
  if(!confirm("⚠️ Delete this file permanently?")) return
  await fetch(`/api/admin/delete/${id}?key=${props.apiKey}`, { method: 'DELETE' })
  loadDashboard()
}
</script>

<template>
  <div class="admin-shell">
    <!-- Ambient Background -->
    <div class="bg-noise"></div>
    <div class="glow-orb"></div>

    <!-- SIDEBAR NAVIGATION -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo-mark">🛡️</div>
        <div class="brand-info">
          <h3>Admin Console</h3>
          <span>System Overview</span>
        </div>
      </div>

      <nav class="nav-menu">
        <div class="nav-label">Management</div>
        <button :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
          User Directory
        </button>
        <button :class="{ active: activeTab === 'files' }" @click="activeTab = 'files'">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>
          File Inspector
        </button>
      </nav>

      <div class="sidebar-footer">
        <button class="logout-btn" @click="$emit('logout')">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
          End Session
        </button>
      </div>
    </aside>

    <!-- MAIN CONTENT -->
    <main class="main-view">
      
      <!-- HEADER -->
      <header class="view-header">
        <div class="header-titles">
          <h1>{{ activeTab === 'users' ? 'Users' : 'Files' }}</h1>
          <span class="count-badge">{{ activeTab === 'users' ? data.users.length : data.files.length }} records</span>
        </div>
        <button class="refresh-btn" @click="loadDashboard" :disabled="loading">
          <svg :class="{ 'spinning': loading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
        </button>
      </header>

      <!-- DATA AREA -->
      <div class="data-container">
        <!-- LOADING OVERLAY -->
        <div v-if="loading" class="loading-overlay">
          <div class="spinner"></div>
        </div>

        <!-- USERS TABLE -->
        <div v-if="activeTab === 'users'" class="table-card">
          <table>
            <thead>
              <tr>
                <th class="col-main">User Entity</th>
                <th>Access Status</th>
                <th>Daily Limit</th>
                <th class="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in data.users" :key="u.email">
                <td class="col-main">
                  <div class="user-cell">
                    <div class="avatar">{{ u.email.charAt(0).toUpperCase() }}</div>
                    <span class="email-text">{{ u.email }}</span>
                  </div>
                </td>
                <td>
                  <span :class="['status-pill', u.status]">
                    <span class="dot"></span> {{ u.status }}
                  </span>
                </td>
                <td class="mono-num">{{ u.limit || 50 }}</td>
                <td class="col-actions">
                  <div class="action-group">
                    <button v-if="u.status === 'PENDING'" @click="updateUserStatus(u.email, 'APPROVE')" class="btn-xs btn-approve" title="Approve">✓ Approve</button>
                    <button v-if="u.status === 'ACTIVE'" @click="updateUserStatus(u.email, 'BAN')" class="btn-xs btn-ban" title="Ban Access">Ban</button>
                    <button v-if="u.status === 'BANNED'" @click="updateUserStatus(u.email, 'APPROVE')" class="btn-xs btn-neutral" title="Restore Access">Unban</button>
                    
                    <button @click="updateUserLimit(u.email)" class="btn-icon" title="Edit Limits">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                    </button>
                    <button @click="deleteUser(u.email)" class="btn-icon danger" title="Delete User">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="data.users.length === 0 && !loading" class="empty-state">No users found.</div>
        </div>

        <!-- FILES TABLE -->
        <div v-if="activeTab === 'files'" class="table-card">
          <table>
            <thead>
              <tr>
                <th class="col-main">Filename / ID</th>
                <th>Sender</th>
                <th>Type</th>
                <th>Activity</th>
                <th class="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in data.files" :key="f.id">
                <td class="col-main">
                  <div class="file-cell">
                    <span class="filename" :title="f.filename">{{ f.filename }}</span>
                    <span class="file-id mono-num">ID: {{ f.id }}</span>
                  </div>
                </td>
                <td><span class="sender-tag">{{ f.sender }}</span></td>
                <td>
                  <span v-if="f.protected" class="badge-lock">🔒 Protected</span>
                  <span v-else class="badge-public">Public</span>
                </td>
                <td class="mono-num">{{ f.downloads }} dwnlds</td>
                <td class="col-actions">
                  <button @click="deleteFile(f.id)" class="btn-xs btn-delete">
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="data.files.length === 0 && !loading" class="empty-state">No active transfers.</div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* --- LAYOUT & BASE --- */
.admin-shell {
  display: flex;
  width: 100vw;
  height: 100vh;
  background-color: #020617; /* Slate 950 */
  color: #f8fafc;
  font-family: 'Inter', sans-serif;
  overflow: hidden;
  position: relative;
}

.bg-noise { position: absolute; inset: 0; opacity: 0.04; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E"); pointer-events: none; z-index: 0; }
.glow-orb { position: absolute; top: -100px; left: -100px; width: 500px; height: 500px; background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%); border-radius: 50%; pointer-events: none; z-index: 0; }

/* --- SIDEBAR --- */
.sidebar {
  width: 260px;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(255,255,255,0.08);
  display: flex;
  flex-direction: column;
  padding: 24px;
  z-index: 10;
}

.sidebar-header { display: flex; align-items: center; gap: 12px; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.logo-mark { width: 36px; height: 36px; background: linear-gradient(135deg, #6366f1, #4f46e5); border-radius: 8px; display: grid; place-items: center; font-size: 1.2rem; box-shadow: 0 0 15px rgba(99,102,241,0.3); }
.brand-info h3 { font-size: 1rem; font-weight: 700; color: white; margin: 0; }
.brand-info span { font-size: 0.75rem; color: #94a3b8; }

.nav-menu { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.nav-label { font-size: 0.75rem; text-transform: uppercase; color: #64748b; font-weight: 600; margin-bottom: 8px; margin-left: 8px; letter-spacing: 0.05em; }
.nav-menu button { display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: transparent; border: none; color: #94a3b8; cursor: pointer; border-radius: 8px; font-size: 0.9rem; font-weight: 500; transition: all 0.2s; }
.nav-menu button .icon { width: 18px; height: 18px; }
.nav-menu button:hover { background: rgba(255,255,255,0.03); color: white; }
.nav-menu button.active { background: rgba(99, 102, 241, 0.1); color: #818cf8; font-weight: 600; }

.sidebar-footer { border-top: 1px solid rgba(255,255,255,0.05); padding-top: 20px; }
.logout-btn { display: flex; align-items: center; gap: 10px; color: #ef4444; background: none; border: none; font-size: 0.9rem; font-weight: 500; cursor: pointer; opacity: 0.8; transition: 0.2s; width: 100%; padding: 8px; border-radius: 6px; }
.logout-btn:hover { background: rgba(239, 68, 68, 0.1); opacity: 1; }
.logout-btn .icon { width: 16px; height: 16px; }

/* --- MAIN VIEW --- */
.main-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; z-index: 5; }

.view-header { display: flex; justify-content: space-between; align-items: flex-end; padding: 32px 40px; background: linear-gradient(180deg, rgba(15,23,42,0.8) 0%, transparent 100%); z-index: 10; }
.header-titles h1 { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; color: white; line-height: 1; }
.count-badge { display: inline-block; margin-top: 8px; font-size: 0.85rem; color: #94a3b8; font-family: 'JetBrains Mono', monospace; }
.refresh-btn { width: 36px; height: 36px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: white; cursor: pointer; display: grid; place-items: center; transition: 0.2s; }
.refresh-btn:hover { background: rgba(255,255,255,0.1); color: #818cf8; }
.refresh-btn svg { width: 18px; height: 18px; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* --- DATA CONTAINER --- */
.data-container { flex: 1; padding: 0 40px 40px; overflow-y: auto; position: relative; }

.table-card { background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; overflow: hidden; backdrop-filter: blur(5px); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
table { width: 100%; border-collapse: collapse; text-align: left; }

thead th { background: rgba(15, 23, 42, 0.8); color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 16px 24px; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.1); }
tbody tr { border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.15s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(255,255,255,0.02); }
td { padding: 16px 24px; font-size: 0.9rem; vertical-align: middle; color: #e2e8f0; }

.col-main { width: 40%; }
.col-actions { text-align: right; }

/* USER CELLS */
.user-cell { display: flex; align-items: center; gap: 12px; }
.avatar { width: 32px; height: 32px; background: #334155; color: #cbd5e1; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 0.8rem; border: 1px solid rgba(255,255,255,0.1); }
.email-text { font-weight: 500; }

/* FILE CELLS */
.file-cell { display: flex; flex-direction: column; }
.filename { font-weight: 500; color: white; }
.file-id { font-size: 0.75rem; color: #64748b; margin-top: 2px; }
.sender-tag { font-size: 0.85rem; color: #cbd5e1; background: rgba(255,255,255,0.05); padding: 4px 8px; border-radius: 4px; }

/* STATUS BADGES */
.status-pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; border: 1px solid transparent; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.PENDING { background: rgba(245, 158, 11, 0.1); color: #fbbf24; border-color: rgba(245, 158, 11, 0.2); } .PENDING .dot { background: #fbbf24; box-shadow: 0 0 5px #fbbf24; }
.ACTIVE { background: rgba(16, 185, 129, 0.1); color: #34d399; border-color: rgba(16, 185, 129, 0.2); } .ACTIVE .dot { background: #34d399; box-shadow: 0 0 5px #34d399; }
.BANNED { background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239, 68, 68, 0.2); } .BANNED .dot { background: #f87171; }

.badge-lock { font-size: 0.75rem; color: #facc15; font-weight: 500; display: flex; align-items: center; gap: 4px; }
.badge-public { font-size: 0.75rem; color: #94a3b8; }

/* NUMBERS */
.mono-num { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #cbd5e1; }

/* BUTTONS */
.action-group { display: flex; justify-content: flex-end; gap: 8px; align-items: center; }
.btn-xs { padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; cursor: pointer; border: 1px solid transparent; transition: 0.2s; }
.btn-approve { background: rgba(16, 185, 129, 0.15); color: #34d399; } .btn-approve:hover { background: rgba(16, 185, 129, 0.25); }
.btn-ban { background: rgba(239, 68, 68, 0.15); color: #f87171; } .btn-ban:hover { background: rgba(239, 68, 68, 0.25); }
.btn-neutral { background: #334155; color: white; }
.btn-delete { background: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); } .btn-delete:hover { background: #ef4444; color: white; }

.btn-icon { background: transparent; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; width: 28px; height: 28px; display: grid; place-items: center; color: #94a3b8; cursor: pointer; transition: 0.2s; }
.btn-icon svg { width: 14px; height: 14px; }
.btn-icon:hover { border-color: #6366f1; color: #6366f1; background: rgba(99,102,241,0.05); }
.btn-icon.danger:hover { border-color: #ef4444; color: #ef4444; background: rgba(239,68,68,0.05); }

/* LOADING & EMPTY STATES */
.loading-overlay { position: absolute; inset: 0; background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(2px); z-index: 20; display: grid; place-items: center; }
.spinner { width: 40px; height: 40px; border: 3px solid rgba(255,255,255,0.1); border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite; }
.empty-state { padding: 40px; text-align: center; color: #64748b; font-size: 0.9rem; }
</style>