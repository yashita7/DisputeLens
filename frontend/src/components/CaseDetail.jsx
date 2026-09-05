import { useState, useEffect } from 'react'
import './CaseDetail.css'

const API_BASE = 'http://localhost:8000'
const STAGGER_DELAY = 180 // ms between evidence items

function CaseDetail({ caseId, onBack }) {
  const [caseData, setCaseData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [visibleItems, setVisibleItems] = useState([])
  const [showConfidence, setShowConfidence] = useState(false)
  const [showDecision, setShowDecision] = useState(false)
  const [expandedItems, setExpandedItems] = useState(new Set())
  
  // Check for debug mode from URL params
  const urlParams = new URLSearchParams(window.location.search)
  const debugMode = urlParams.get('debug') === 'true'

  useEffect(() => {
    setLoading(true)
    setVisibleItems([])
    setShowConfidence(false)
    setShowDecision(false)
    setExpandedItems(new Set())

    fetch(`${API_BASE}/chargebacks/${caseId}`)
      .then(res => res.json())
      .then(data => {
        setCaseData(data)
        setLoading(false)
        
        // Stagger evidence reveal
        data.evidence.forEach((_, index) => {
          setTimeout(() => {
            setVisibleItems(prev => [...prev, index])
          }, index * STAGGER_DELAY)
        })
        
        // Show confidence gauge after all evidence
        setTimeout(() => {
          setShowConfidence(true)
        }, data.evidence.length * STAGGER_DELAY + 200)
        
        // Show decision last
        setTimeout(() => {
          setShowDecision(true)
        }, data.evidence.length * STAGGER_DELAY + 600)
      })
      .catch(err => {
        console.error('Failed to load case:', err)
        setLoading(false)
      })
  }, [caseId])

  const toggleExpand = (index) => {
    const newSet = new Set(expandedItems)
    if (newSet.has(index)) {
      newSet.delete(index)
    } else {
      newSet.add(index)
    }
    setExpandedItems(newSet)
  }

  const getDecisionColor = (decision) => {
    switch(decision) {
      case 'CONTEST': return 'var(--green)'
      case 'REVIEW': return 'var(--amber)'
      case 'DO_NOT_CONTEST': return 'var(--red)'
      default: return 'var(--text-secondary)'
    }
  }

  const getConfidencePercent = (score) => {
    // Score ranges from 0 to 100 (sum of all positive rule weights)
    // Map directly to percentage for gauge display
    return Math.min(100, Math.max(0, score))
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading case details...</p>
      </div>
    )
  }

  if (!caseData) {
    return <div className="error">Case not found</div>
  }

  const confidencePercent = getConfidencePercent(caseData.score)

  return (
    <div className="case-detail">
      <button className="back-button" onClick={onBack}>← Back to Cases</button>
      
      <div className="case-header">
        <div>
          <h1 className="mono">{caseData.chargeback_id}</h1>
          <p className="case-meta">
            <span className="mono">{caseData.transaction_id}</span> • 
            <span className="mono">${caseData.amount.toFixed(2)}</span> • 
            <span>{caseData.reason_code}</span>
          </p>
        </div>
      </div>

      {/* Decision Badge (reveals last) */}
      <div className={`decision-reveal ${showDecision ? 'visible' : ''}`}>
        <span className={`badge ${caseData.decision}`} style={{ fontSize: '1rem', padding: '0.5rem 1.5rem' }}>
          {caseData.decision}
        </span>
      </div>

      {/* Confidence Gauge */}
      <div className={`confidence-section ${showConfidence ? 'visible' : ''}`}>
        <h3>Confidence: {caseData.confidence}</h3>
        <div className="confidence-gauge">
          <div 
            className="confidence-fill"
            style={{ 
              width: `${confidencePercent}%`,
              background: getDecisionColor(caseData.decision)
            }}
          ></div>
        </div>
        <div className="confidence-meta mono">Score: {caseData.score}</div>
      </div>

      {/* LLM Summary (if available) - SHOWN FIRST, BEFORE EVIDENCE */}
      {caseData.llm_summary && !caseData.llm_summary.error && (
        <section className="llm-section">
          <h2>Case Summary</h2>
          <div className="llm-summary">
            <p>{caseData.llm_summary.summary}</p>
          </div>
          
          {caseData.llm_summary.gaps && caseData.llm_summary.gaps.length > 0 && (
            <div className="llm-gaps">
              <h4>Identified Gaps:</h4>
              <ul>
                {caseData.llm_summary.gaps.map((gap, i) => (
                  <li key={i}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {!caseData.llm_summary && (
        <div className="llm-note">
          <p>💡 LLM summary not available. Set GEMINI_API_KEY to enable AI-generated case summaries.</p>
        </div>
      )}

      {/* Evidence Items */}
      <section className="evidence-section">
        <h2>Evidence</h2>
        <div className="evidence-list">
          {caseData.evidence.map((item, index) => {
            const isVisible = visibleItems.includes(index)
            const isExpanded = expandedItems.has(index)
            
            return (
              <div 
                key={index}
                className={`evidence-item ${isVisible ? 'visible' : ''} ${item.is_gap ? 'gap' : ''} ${item.is_dependent_gap ? 'dependent-gap' : ''}`}
                onClick={() => isVisible && toggleExpand(index)}
              >
                <div className="evidence-main">
                  {!item.is_gap && <span className="check-icon">✓</span>}
                  <div className="evidence-content">
                    <span className="evidence-label">{item.label}</span>
                    <span className="evidence-value mono">
                      {item.is_gap ? (
                        <>
                          <span className="gap-text">not available</span>
                          {item.is_dependent_gap && <span className="dependent-note"> (dependent)</span>}
                        </>
                      ) : (
                        item.value === 'True' ? 'true' : 
                        item.value === 'False' ? 'false' : 
                        item.value
                      )}
                    </span>
                  </div>
                  {isVisible && <span className="expand-icon">{isExpanded ? '−' : '+'}</span>}
                </div>
                
                {isExpanded && (
                  <div className="evidence-source">
                    <span className="source-label">Source:</span>
                    <code className="mono">{item.source_field} = {item.value}</code>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* Evidence Gaps Summary */}
      {caseData.gaps && caseData.gaps.length > 0 && (
        <section className="gaps-section">
          <h3>Evidence Gaps</h3>
          <div className="gaps-list">
            {caseData.gaps.map((gap, i) => (
              <div key={i} className="gap-item">
                <span>⚠</span>
                <span>{gap.label}</span>
                {gap.is_dependent_gap && <span className="gap-note">(cascaded from {gap.label.includes('Delivered') ? 'Delivery Confirmed' : 'parent field'})</span>}
              </div>
            ))}
          </div>
          {caseData.metadata.masked_field && (
            <p className="gap-explanation">
              Primary masked field: <code className="mono">{caseData.metadata.masked_field}</code>
            </p>
          )}
        </section>
      )}

      {/* Fired Rules */}
      <section className="rules-section">
        <h3>Rule Engine Context</h3>
        <div className="rules-list">
          {caseData.fired_rules.map((rule, i) => (
            <div key={i} className="rule-item">
              <code className="mono">{rule}</code>
            </div>
          ))}
        </div>
      </section>

      {/* Audit Trail */}
      <section className="audit-section">
        <h3>Audit Trail</h3>
        <div className="audit-list">
          {caseData.audit_trail.map((entry, i) => (
            <div key={i} className="audit-item">
              <span className="audit-step">{entry.step}</span>
              <span className="audit-detail">{entry.detail}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Debug metadata (ONLY if ?debug=true in URL) */}
      {debugMode && caseData.metadata.is_noise_case && (
        <section className="debug-section">
          <h4>🔬 Debug Info (Noise Case)</h4>
          <p>Noise Type: <code>{caseData.metadata.noise_type}</code></p>
          <p>True Label: <code>{caseData.metadata.true_label}</code></p>
          <p className="noise-note">
            This case has label noise - the evidence contradicts the ground truth label.
          </p>
        </section>
      )}
    </div>
  )
}

export default CaseDetail
