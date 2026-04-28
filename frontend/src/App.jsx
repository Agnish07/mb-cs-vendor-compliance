import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchDashboardData, runEscalations, uploadSubmission } from './services/api'
import './App.css'

const chartColors = ['#2d7a78', '#d99a21', '#d94747', '#3a9c70', '#7a5c92']

const riskClass = {
  LOW: 'riskLow',
  MEDIUM: 'riskMedium',
  HIGH: 'riskHigh',
}

const trendRiskClass = {
  LOW: 'trendRiskLow',
  MEDIUM: 'trendRiskMedium',
  HIGH: 'trendRiskHigh',
}

function clampRate(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0
  return Math.min(Math.max(numeric, 0), 1)
}

function riskBandForRate(rate) {
  if (rate >= 0.6) return 'HIGH'
  if (rate >= 0.25) return 'MEDIUM'
  return 'LOW'
}

function normalizeTrendData(trendData) {
  return {
    vendors: (trendData?.vendors || []).map((trend) => {
      const recentRate = clampRate(trend.recent_error_rate)
      const forecastRate = clampRate(trend.forecast_next_error_rate)
      const riskBand = trend.risk_band || riskBandForRate(recentRate)
      const dominantError = trend.dominant_error_code || 'no dominant error'
      const fallbackInsight = `${trend.vendor_email} is ${(trend.trajectory || 'STABLE').toLowerCase()} with ${riskBand.toLowerCase()} current risk and a recent row failure rate of ${Math.round(recentRate * 100)}%; next submission forecast is ${Math.round(forecastRate * 100)}%, driven mainly by ${dominantError}.`
      const aiInsight = typeof trend.insight === 'string' ? trend.insight.trim() : ''

      return {
        ...trend,
        latest_error_rate: clampRate(trend.latest_error_rate),
        baseline_error_rate: clampRate(trend.baseline_error_rate),
        recent_error_rate: recentRate,
        forecast_next_error_rate: forecastRate,
        risk_band: riskBand,
        insight: aiInsight || fallbackInsight,
      }
    }),
    timeline: (trendData?.timeline || []).map((point) => ({
      ...point,
      error_rate: clampRate(point.error_rate),
    })),
    top_error_codes: trendData?.top_error_codes || [],
    top_triage_categories: trendData?.top_triage_categories || [],
  }
}

function App() {
  const [submissions, setSubmissions] = useState([])
  const [errors, setErrors] = useState([])
  const [risks, setRisks] = useState([])
  const [escalations, setEscalations] = useState([])
  const [correctEntries, setCorrectEntries] = useState([])
  const [trends, setTrends] = useState({
    vendors: [],
    timeline: [],
    top_error_codes: [],
    top_triage_categories: [],
  })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [uploading, setUploading] = useState(false)
  const [vendorEmail, setVendorEmail] = useState('vendor@example.com')
  const [file, setFile] = useState(null)

  async function loadDashboard() {
    setLoading(true)
    setMessage('')
    try {
      const data = await fetchDashboardData()
      setSubmissions(data.submissions)
      setErrors(data.errors)
      setRisks(data.risks)
      setEscalations(data.escalations)
      setCorrectEntries(data.correctEntries)
      setTrends(normalizeTrendData(data.trends))
    } catch (error) {
      setMessage(
        error.code === 'ECONNABORTED'
          ? 'The compliance API is still processing. Try refresh in a moment.'
          : error.response?.data?.detail || 'Unable to reach the compliance API',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  const summary = useMemo(() => {
    const vendors = new Set(submissions.map((submission) => submission.vendor_email))
    const rows = submissions.reduce((total, submission) => total + submission.total_rows, 0)

    return {
      totalSubmissions: submissions.length,
      totalErrors: errors.length,
      vendorCount: vendors.size,
      totalRows: rows,
      openEscalations: escalations.length,
      correctEntries: correctEntries.length,
    }
  }, [submissions, errors, escalations, correctEntries])

  const errorDistribution = useMemo(() => {
    const counts = errors.reduce((acc, error) => {
      acc[error.error_code] = (acc[error.error_code] || 0) + 1
      return acc
    }, {})
    return Object.entries(counts).map(([name, value]) => ({ name, value }))
  }, [errors])

  const errorsPerVendor = useMemo(() => {
    const counts = submissions.reduce((acc, submission) => {
      acc[submission.vendor_email] = (acc[submission.vendor_email] || 0) + submission.error_count
      return acc
    }, {})
    return Object.entries(counts).map(([vendor, count]) => ({ vendor, count }))
  }, [submissions])

  async function handleUpload(event) {
    event.preventDefault()
    if (!file) {
      setMessage('Choose a CSV or XLSX file before uploading')
      return
    }

    setUploading(true)
    setMessage('')
    try {
      const result = await uploadSubmission({ file, vendorEmail })
      setMessage(`Processed ${result.submission.file_name}: ${result.errors.length} errors found`)
      setFile(null)
      event.target.reset()
      await loadDashboard()
    } catch (error) {
      setMessage(
        error.code === 'ECONNABORTED'
          ? 'Upload is still processing AI governance checks. Try refresh in a moment.'
          : error.response?.data?.detail || 'Upload failed',
      )
    } finally {
      setUploading(false)
    }
  }

  async function handleRunEscalations() {
    setMessage('')
    try {
      const escalated = await runEscalations()
      setMessage(`Escalation cycle completed: ${escalated.length} overdue submissions reviewed`)
      await loadDashboard()
    } catch (error) {
      setMessage(
        error.code === 'ECONNABORTED'
          ? 'Escalation cycle is still processing AI checks. Try refresh in a moment.'
          : error.response?.data?.detail || 'Escalation cycle failed',
      )
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Autonomous Vendor Compliance</p>
          <h1>Customs duty control center</h1>
        </div>
        <button className="ghostButton" type="button" onClick={loadDashboard} disabled={loading}>
          Refresh
        </button>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="metrics" aria-label="Dashboard overview">
        <article>
          <span>Total submissions</span>
          <strong>{summary.totalSubmissions}</strong>
        </article>
        <article>
          <span>Total errors</span>
          <strong>{summary.totalErrors}</strong>
        </article>
        <article>
          <span>Vendors</span>
          <strong>{summary.vendorCount}</strong>
        </article>
        <article>
          <span>Rows inspected</span>
          <strong>{summary.totalRows}</strong>
        </article>
        <article>
          <span>Open escalations</span>
          <strong>{summary.openEscalations}</strong>
        </article>
        <article>
          <span>Correct entries</span>
          <strong>{summary.correctEntries}</strong>
        </article>
      </section>

      <section className="workbench">
        <form className="uploadPanel" onSubmit={handleUpload}>
          <div>
            <h2>Manual intake</h2>
            <p>Runs the same normalization, validation, classification, and remediation pipeline.</p>
          </div>
          <label>
            Vendor email
            <input
              value={vendorEmail}
              onChange={(event) => setVendorEmail(event.target.value)}
              type="email"
              required
            />
          </label>
          <label>
            Duty file
            <input
              accept=".csv,.xlsx,.xls,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              type="file"
            />
          </label>
          <button className="primaryButton" type="submit" disabled={uploading}>
            {uploading ? 'Processing' : 'Upload'}
          </button>
        </form>

        <section className="riskPanel">
          <div className="sectionHeader">
            <h2>Vendor risk</h2>
            <span>{risks.length} scored</span>
          </div>
          <div className="riskList">
            {risks.length === 0 && <p className="emptyState">No vendor history yet.</p>}
            {risks.map((risk) => (
              <article className={`riskItem ${riskClass[risk.risk_level]}`} key={risk.vendor_email}>
                <div>
                  <strong>{risk.vendor_email}</strong>
                  <span>
                    {risk.error_count} errors across {risk.submissions} submissions
                  </span>
                  {risk.ai_insight && <em>{risk.ai_insight}</em>}
                </div>
                <b>{risk.risk_score}</b>
              </article>
            ))}
          </div>
        </section>
      </section>

      <section className="governance">
        <article>
          <div className="sectionHeader">
            <h2>Escalation governance</h2>
            <button className="ghostButton" type="button" onClick={handleRunEscalations}>
              Run cycle
            </button>
          </div>
          <div className="escalationList">
            {escalations.length === 0 && <p className="emptyState">No overdue correction loops.</p>}
            {escalations.map((submission) => (
              <div className="escalationItem" key={submission.id}>
                <div>
                  <strong>{submission.vendor_email}</strong>
                  <span>{submission.file_name}</span>
                </div>
                <span>Level {submission.escalation_level}</span>
                <span>{submission.correction_due_at ? new Date(submission.correction_due_at).toLocaleString() : 'No due date'}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="charts">
        <article className="trendPanel">
          <div className="sectionHeader">
            <h2>Trend mining</h2>
            <span>{trends.vendors.length} vendor trajectories</span>
          </div>
          <div className="trendList">
            {trends.vendors.length === 0 && <p className="emptyState">No trend history yet.</p>}
            {trends.vendors.map((trend) => (
              <div className={`trendItem trajectory${trend.trajectory}`} key={trend.vendor_email}>
                <div>
                  <strong>{trend.vendor_email}</strong>
                  <span>{trend.insight}</span>
                </div>
                <div className="trendBadges">
                  <b className={trendRiskClass[trend.risk_band]}>{trend.risk_band} RISK</b>
                  <b>{trend.trajectory}</b>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Error-rate trajectory</h2>
            <span>{trends.timeline.length} submissions</span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trends.timeline}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="submission_id" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} />
              <Tooltip formatter={(value) => `${Math.round(value * 100)}%`} />
              <Line type="monotone" dataKey="error_rate" stroke="#d94747" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Error distribution</h2>
            <span>{errors.length} logged</span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={errorDistribution}
                dataKey="value"
                nameKey="name"
                innerRadius={55}
                outerRadius={92}
                paddingAngle={3}
              >
                {errorDistribution.map((entry, index) => (
                  <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Errors per vendor</h2>
            <span>{summary.vendorCount} vendors</span>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={errorsPerVendor} layout="vertical" margin={{ top: 10, right: 18, left: 18, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis allowDecimals={false} type="number" />
              <YAxis dataKey="vendor" interval={0} tick={{ fontSize: 10 }} type="category" width={190} />
              <Tooltip />
              <Bar dataKey="count" fill="#2d7a78" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Recurring error codes</h2>
            <span>{trends.top_error_codes.length} signals</span>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={trends.top_error_codes} layout="vertical" margin={{ top: 10, right: 18, left: 18, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis allowDecimals={false} type="number" />
              <YAxis dataKey="error_code" interval={0} tick={{ fontSize: 10 }} type="category" width={190} />
              <Tooltip />
              <Bar dataKey="count" fill="#d99a21" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>
      </section>

      <section className="tables">
        <article>
          <div className="sectionHeader">
            <h2>Correct entries</h2>
            <span>{correctEntries.length} rows</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>File</th>
                  <th>Row</th>
                  <th>Part number</th>
                  <th>Description</th>
                  <th>HSN/RITC</th>
                  <th>BCD</th>
                  <th>CVD</th>
                  <th>SWS</th>
                  <th>IGST</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {correctEntries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.vendor_email}</td>
                    <td>{entry.file_name}</td>
                    <td>{entry.row_number}</td>
                    <td>{entry.part_number}</td>
                    <td>{entry.description}</td>
                    <td>{entry.hsn_code}</td>
                    <td>{entry.bcd ?? '-'}</td>
                    <td>{entry.cvd ?? '-'}</td>
                    <td>{entry.sws ?? '-'}</td>
                    <td>{entry.igst ?? '-'}</td>
                    <td>{new Date(entry.upload_time).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {correctEntries.length === 0 && <p className="emptyState">No valid rows captured yet.</p>}
          </div>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Submission history</h2>
            <span>{loading ? 'Loading' : `${submissions.length} records`}</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>File</th>
                  <th>Rows</th>
                  <th>Errors</th>
                  <th>Status</th>
                  <th>Due</th>
                  <th>Audit narrative</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {submissions.map((submission) => (
                  <tr key={submission.id}>
                    <td>{submission.vendor_email}</td>
                    <td>{submission.file_name}</td>
                    <td>{submission.total_rows}</td>
                    <td>{submission.error_count}</td>
                    <td>{submission.status}</td>
                    <td>{submission.correction_due_at ? new Date(submission.correction_due_at).toLocaleString() : '-'}</td>
                    <td>{submission.ai_audit_summary || '-'}</td>
                    <td>{new Date(submission.upload_time).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {submissions.length === 0 && <p className="emptyState">No submissions processed.</p>}
          </div>
        </article>

        <article>
          <div className="sectionHeader">
            <h2>Error logs</h2>
            <span>{errors.length} records</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Code</th>
                  <th>Severity</th>
                  <th>Type</th>
                  <th>Triage</th>
                  <th>AI recommendation</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {errors.map((error) => (
                  <tr key={error.id}>
                    <td>{error.row_number}</td>
                    <td>{error.error_code}</td>
                    <td>
                      <span className={`severity severity${error.severity}`}>{error.severity}</span>
                    </td>
                    <td>{error.error_type}</td>
                    <td>{error.triage_category}</td>
                    <td>{error.ai_recommendation}</td>
                    <td>{error.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {errors.length === 0 && <p className="emptyState">No validation errors logged.</p>}
          </div>
        </article>
      </section>
    </main>
  )
}

export default App
