import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8010',
  timeout: 90000,
})

export async function fetchDashboardData() {
  const [submissions, errors, risks, escalations, correctEntries, trends] = await Promise.all([
    api.get('/submissions'),
    api.get('/errors'),
    api.get('/vendor-risk'),
    api.get('/escalations'),
    api.get('/correct-entries'),
    api.get('/trend-insights'),
  ])

  return {
    submissions: submissions.data,
    errors: errors.data,
    risks: risks.data,
    escalations: escalations.data,
    correctEntries: correctEntries.data,
    trends: trends.data,
  }
}

export async function uploadSubmission({ file, vendorEmail }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('vendor_email', vendorEmail)

  const response = await api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

  return response.data
}

export async function runEscalations() {
  const response = await api.post('/run-escalations')
  return response.data
}

export default api
