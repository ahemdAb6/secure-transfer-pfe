<script setup>
import { ref } from 'vue'

const emit = defineEmits(['login-success', 'admin-login', 'go-admin'])

const isRegistering = ref(false)
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref(null)


const registrationSuccess = ref(false)

const handleSubmit = async () => {
  if (!email.value || !password.value) return
  
  loading.value = true
  error.value = null
  
  const endpoint = isRegistering.value ? '/api/auth/register' : '/api/auth/login'
  const formData = new FormData()
  formData.append('email', email.value)
  formData.append('password', password.value)

  try {
    const res = await fetch(endpoint, { method: 'POST', body: formData })
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || "Authentication Failed")
    }

    const data = await res.json()

    if (isRegistering.value) {

      registrationSuccess.value = true
    } else {
      if (data.role === 'ADMIN') {
        emit('admin-login', { token: data.token, email: data.email, role: 'ADMIN' })
      } else {
        emit('login-success', { token: data.token, email: data.email, role: 'USER' })
      }
    }

  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
const resetToLogin = () => {
  isRegistering.value = false
  registrationSuccess.value = false
  email.value = ''
  password.value = ''
  error.value = null
}
</script>

<template>
  <div class="login-container">
    
    <Transition name="fade" mode="out-in">
      <div v-if="registrationSuccess" class="success-panel">
        <div class="icon-circle">⏳</div>
        <h2>Request Submitted</h2>
        <p class="success-text">
          Your account has been created and is <strong>pending approval</strong>.
          <br><br>
          Please wait until an Administrator activates your account before logging in.
        </p>
        <button class="submit-btn" @click="resetToLogin">Return to Login</button>
      </div>

      <div v-else class="form-panel">
        <div class="header">
          <div class="logo-wrapper">
            <svg class="logo-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path></svg>
          </div>
          <h2 class="title">{{ isRegistering ? 'Create Account' : 'Welcome Back' }}</h2>
          <p class="subtitle">{{ isRegistering ? 'Join the secure network.' : 'Enter your credentials to access.' }}</p>
        </div>

        <form @submit.prevent="handleSubmit" class="auth-form">
          <div class="input-group">
            <label>Email Address</label>
            <div class="input-wrapper">
              <input v-model="email" type="email" placeholder="name@company.com" class="input-field" required>
            </div>
          </div>

          <div class="input-group">
            <label>Password</label>
            <div class="input-wrapper">
              <input v-model="password" type="password" placeholder="••••••••" class="input-field" required>
              <button type="button" class="eye-btn" @click="(e) => {
                  const input = e.currentTarget.parentElement.querySelector('input');
                  input.type = input.type === 'password' ? 'text' : 'password';
                }">👁️</button>
            </div>
          </div>
          
          <button type="submit" class="submit-btn" :disabled="loading">
            <span v-if="loading" class="loader"></span>
            <span>{{ loading ? 'Processing...' : (isRegistering ? 'Request Access' : 'Sign In') }}</span>
          </button>

          <div v-if="error" class="error-box">⚠️ {{ error }}</div>
        </form>

        <div class="footer">
          <div class="toggle-text">
            {{ isRegistering ? 'Already have an account?' : 'New to Axelites?' }}
            <button class="link-btn" @click="isRegistering = !isRegistering">
              {{ isRegistering ? 'Log in' : 'Create account' }}
            </button>
          </div>
          <button class="admin-trigger" @click="$emit('go-admin')">🛡️ Admin</button>
        </div>
      </div>
    </Transition>

  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

* { box-sizing: border-box; }
.login-container { width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; font-family: 'Inter', sans-serif; color: #f8fafc; }

.success-panel { text-align: center; padding: 20px; animation: slideUp 0.4s ease; }
.icon-circle { width: 64px; height: 64px; background: rgba(245, 158, 11, 0.1); color: #fbbf24; border-radius: 50%; display: grid; place-items: center; font-size: 32px; margin: 0 auto 20px; border: 1px solid rgba(245, 158, 11, 0.2); }
.success-panel h2 { font-size: 1.5rem; margin-bottom: 10px; color: white; }
.success-text { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; margin-bottom: 30px; }
.success-text strong { color: #fbbf24; }
.form-panel { animation: fadeIn 0.5s ease; }
.header { text-align: center; margin-bottom: 32px; }
.logo-wrapper { width: 48px; height: 48px; background: linear-gradient(135deg, #6366f1, #818cf8); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; box-shadow: 0 0 25px rgba(99, 102, 241, 0.4); color: white; }
.logo-svg { width: 24px; height: 24px; }
.title { font-size: 1.75rem; font-weight: 600; margin-bottom: 8px; color: white; }
.subtitle { font-size: 0.95rem; color: #94a3b8; }

.auth-form { display: flex; flex-direction: column; gap: 20px; }
.input-group label { display: block; font-size: 0.85rem; font-weight: 500; color: #94a3b8; margin-bottom: 8px; }
.input-wrapper { position: relative; display: flex; align-items: center; }
.input-field { width: 100%; padding: 12px 16px; background: rgba(0, 0, 0, 0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; color: white; font-size: 1rem; outline: none; transition: 0.2s; }
.input-field:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2); }
.eye-btn { position: absolute; right: 12px; background: none; border: none; cursor: pointer; opacity: 0.6; }

.submit-btn { margin-top: 10px; width: 100%; padding: 14px; background: linear-gradient(180deg, #6366f1 0%, #4f46e5 100%); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; color: white; font-weight: 600; font-size: 1rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; }
.submit-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }

.error-box { background: rgba(220, 38, 38, 0.1); border: 1px solid rgba(220, 38, 38, 0.3); color: #f87171; padding: 10px 14px; border-radius: 8px; font-size: 0.9rem; margin-top: 10px; }

.footer { margin-top: 30px; display: flex; flex-direction: column; align-items: center; gap: 20px; }
.toggle-text { color: #94a3b8; font-size: 0.9rem; }
.link-btn { background: none; border: none; color: #6366f1; font-weight: 600; cursor: pointer; margin-left: 4px; }
.link-btn:hover { text-decoration: underline; }
.admin-trigger { background: transparent; border: 1px solid rgba(255,255,255,0.1); padding: 5px 10px; border-radius: 20px; color: rgba(255,255,255,0.5); font-size: 0.75rem; cursor: pointer; }
.admin-trigger:hover { color: #10b981; border-color: #10b981; }

.loader { width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>