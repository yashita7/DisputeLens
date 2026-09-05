import { useState, useEffect } from 'react'
import './MetricsView.css'

const API_BASE = 'http://localhost:8000'

function MetricsView() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/metrics`)
      .then(res => res.json())
      .then(data => {
        setMetrics(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to load metrics:', err)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading metrics...</p>
      </div>
    )
  }

  if (!metrics) {
    return <div className="error">Failed to load metrics</div>
  }

  const cm = metrics.confusion_matrix
  const maxVal = Math.max(cm.true_positive, cm.false_positive, cm.true_negative, cm.false_negative)

  return (
    <div className="metrics-view">
      <h1>System Performance Metrics</h1>
      <p className="metrics-subtitle">Evaluated on {metrics.total_cases} dev set cases</p>

      {/* Key Metrics */}
      <section className="key-metrics">
        <div className="metric-card">
          <div className="metric-value">{(metrics.precision * 100).toFixed(1)}%</div>
          <div className="metric-label">Precision</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{(metrics.recall * 100).toFixed(1)}%</div>
          <div className="metric-label">Recall</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{(metrics.f1_score * 100).toFixed(1)}%</div>
          <div className="metric-label">F1 Score</div>
        </div>
        <div className="metric-card highlight">
          <div className="metric-value">{(metrics.escalation_rate * 100).toFixed(1)}%</div>
          <div className="metric-label">Escalation Rate</div>
          <div className="metric-note">{metrics.escalated_count} cases to human review</div>
        </div>
      </section>

      {/* Confusion Matrix Heatmap */}
      <section className="confusion-section">
        <h2>Confusion Matrix</h2>
        <div className="confusion-matrix">
          <div className="matrix-corner"></div>
          
          <div className="matrix-label-actual">
            <span>Actual</span>
          </div>
          
          <div className="matrix-label-predicted">
            <span>Predicted</span>
          </div>
          
          <div className="matrix-col-header">Defensible</div>
          <div className="matrix-col-header">Not Defensible</div>
          
          <div className="matrix-row-header">Contest</div>
          <div 
            className="matrix-cell tp"
            style={{ opacity: 0.3 + (0.7 * cm.true_positive / maxVal) }}
          >
            <div className="cell-label">True Positive</div>
            <div className="cell-value">{cm.true_positive}</div>
          </div>
          <div 
            className="matrix-cell fp"
            style={{ opacity: 0.3 + (0.7 * cm.false_positive / maxVal) }}
          >
            <div className="cell-label">False Positive</div>
            <div className="cell-value">{cm.false_positive}</div>
          </div>
          
          <div className="matrix-row-header">Don't Contest</div>
          <div 
            className="matrix-cell fn"
            style={{ opacity: 0.3 + (0.7 * cm.false_negative / maxVal) }}
          >
            <div className="cell-label">False Negative</div>
            <div className="cell-value">{cm.false_negative}</div>
          </div>
          <div 
            className="matrix-cell tn"
            style={{ opacity: 0.3 + (0.7 * cm.true_negative / maxVal) }}
          >
            <div className="cell-label">True Negative</div>
            <div className="cell-value">{cm.true_negative}</div>
          </div>
        </div>
      </section>

      {/* Performance Bars */}
      <section className="bars-section">
        <h2>Performance Overview</h2>
        <div className="bars-container">
          <div className="bar-item">
            <div className="bar-header">
              <span>Precision</span>
              <span className="mono">{(metrics.precision * 100).toFixed(1)}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${metrics.precision * 100}%`, background: 'var(--green)' }}></div>
            </div>
          </div>
          <div className="bar-item">
            <div className="bar-header">
              <span>Recall</span>
              <span className="mono">{(metrics.recall * 100).toFixed(1)}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${metrics.recall * 100}%`, background: 'var(--green)' }}></div>
            </div>
          </div>
          <div className="bar-item">
            <div className="bar-header">
              <span>F1 Score</span>
              <span className="mono">{(metrics.f1_score * 100).toFixed(1)}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${metrics.f1_score * 100}%`, background: 'var(--green)' }}></div>
            </div>
          </div>
        </div>
      </section>

      {/* Cost Estimates */}
      <section className="cost-section">
        <h2>Cost Estimates</h2>
        <div className="cost-grid">
          <div className="cost-card">
            <div className="cost-label">False Positive Cost</div>
            <div className="cost-value mono">${metrics.cost_estimates.false_positive_cost.toLocaleString()}</div>
            <div className="cost-note">Lost from incorrectly contesting {cm.false_positive} cases</div>
          </div>
          <div className="cost-card">
            <div className="cost-label">False Negative Cost</div>
            <div className="cost-value mono">${metrics.cost_estimates.false_negative_cost.toLocaleString()}</div>
            <div className="cost-note">Lost potential recovery from {cm.false_negative} cases</div>
          </div>
          <div className="cost-card highlight">
            <div className="cost-label">Total Estimated Cost</div>
            <div className="cost-value mono">${metrics.cost_estimates.total_estimated_cost.toLocaleString()}</div>
            <div className="cost-note">Avg chargeback: ${metrics.cost_estimates.avg_chargeback_amount.toFixed(2)}</div>
          </div>
        </div>
      </section>

      {/* Breakdown: Masked vs Unmasked */}
      <section className="breakdown-section">
        <h2>Performance Breakdown: Evidence Gaps</h2>
        <p className="section-note">How does the system perform when evidence is incomplete?</p>
        <div className="comparison-table">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Cases</th>
                <th>Precision</th>
                <th>Recall</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>Cases with Evidence Gaps</strong>
                  <div className="table-note">Missing delivery confirmation, signatures, etc.</div>
                </td>
                <td className="mono">{metrics.breakdown.masked_cases.total}</td>
                <td className="mono">{(metrics.breakdown.masked_cases.precision * 100).toFixed(1)}%</td>
                <td className="mono">{(metrics.breakdown.masked_cases.recall * 100).toFixed(1)}%</td>
              </tr>
              <tr>
                <td>
                  <strong>Cases with Complete Evidence</strong>
                  <div className="table-note">All key evidence fields available</div>
                </td>
                <td className="mono">{metrics.breakdown.unmasked_cases.total}</td>
                <td className="mono">{(metrics.breakdown.unmasked_cases.precision * 100).toFixed(1)}%</td>
                <td className="mono">{(metrics.breakdown.unmasked_cases.recall * 100).toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Breakdown: Noise vs Regular */}
      <section className="breakdown-section">
        <h2>Performance Breakdown: Label Noise</h2>
        <p className="section-note">Cases where evidence contradicts ground truth (friendly fraud, etc.)</p>
        <div className="comparison-table">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Cases</th>
                <th>Precision</th>
                <th>Recall</th>
              </tr>
            </thead>
            <tbody>
              <tr className="noise-row">
                <td>
                  <strong>Noise Cases</strong>
                  <div className="table-note">Evidence contradicts true label (friendly fraud, etc.)</div>
                </td>
                <td className="mono">{metrics.breakdown.noise_cases.total}</td>
                <td className="mono">{(metrics.breakdown.noise_cases.precision * 100).toFixed(1)}%</td>
                <td className="mono">{(metrics.breakdown.noise_cases.recall * 100).toFixed(1)}%</td>
              </tr>
              <tr>
                <td>
                  <strong>Regular Cases</strong>
                  <div className="table-note">Evidence aligns with true label</div>
                </td>
                <td className="mono">{metrics.breakdown.regular_cases.total}</td>
                <td className="mono">{(metrics.breakdown.regular_cases.precision * 100).toFixed(1)}%</td>
                <td className="mono">{(metrics.breakdown.regular_cases.recall * 100).toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="noise-explanation">
          <strong>Note:</strong> Noise cases are expected to have low precision/recall because the system 
          makes decisions based on available evidence, which contradicts the hidden ground truth label. 
          This is correct behavior - the system shouldn't "know" about friendly fraud without explicit signals.
        </div>
      </section>
    </div>
  )
}

export default MetricsView
