import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

// This app does not use a service worker. If a stale one is registered for this
// origin (e.g. a previous project reused port 5173), it can hijack the page —
// serving an old app shell and manifest, and breaking Vite's HMR socket.
// Proactively remove any service workers and their caches so our app controls the page.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((registrations) => {
    registrations.forEach((registration) => registration.unregister())
  })
  if (window.caches) {
    caches.keys().then((keys) => keys.forEach((key) => caches.delete(key)))
  }
}

createRoot(document.getElementById('root')).render(<App />)
