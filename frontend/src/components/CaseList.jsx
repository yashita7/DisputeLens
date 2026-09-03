import { useState, useEffect } from 'react'
import './CaseList.css'

const API_BASE = 'http://localhost:8000'

function CaseList({ onCaseSelect }) {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('id')
  const [sortDir, setSortDir] = useState('asc')
  const [filterGaps, setFilterGaps] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/chargebacks`)
      .then(res => res.json())
      .then(data => {
        setCases(data.chargebacks)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to load cases:', err)
        setLoading(false)
      })
  }, [])

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortDir('asc')
    }
  }

  const sortedCases = [...cases].sort((a, b) => {
    let aVal = a[sortBy]
    let bVal = b[sortBy]
    
    if (sortBy === 'id') {
      aVal = parseInt(a.id.split('_')[1])
      bVal = parseInt(b.id.split('_')[1])
    }
    
    if (sortDir === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  })

  const filteredCases = filterGaps 
    ? sortedCases.filter(c => c.has_gaps)
    : sortedCases

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading cases...</p>
      </div>
    )
  }

  return (
    <div className="case-list">
      <div className="case-list-header">
        <h2>Chargeback Cases</h2>
        <div className="filters">
          <label className="filter-checkbox">
            <input 
              type="checkbox" 
              checked={filterGaps}
              onChange={(e) => setFilterGaps(e.target.checked)}
            />
            <span>Show only cases with evidence gaps</span>
          </label>
        </div>
      </div>

      <div className="case-count">
        {filteredCases.length} {filteredCases.length === 1 ? 'case' : 'cases'}
        {filterGaps && ` (${cases.filter(c => c.has_gaps).length} with gaps)`}
      </div>

      <table className="case-table">
        <thead>
          <tr>
            <th onClick={() => handleSort('id')} className="sortable">
              ID {sortBy === 'id' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th onClick={() => handleSort('amount')} className="sortable">
              Amount {sortBy === 'amount' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th onClick={() => handleSort('decision')} className="sortable">
              Decision {sortBy === 'decision' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th onClick={() => handleSort('confidence')} className="sortable">
              Confidence {sortBy === 'confidence' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th onClick={() => handleSort('score')} className="sortable">
              Score {sortBy === 'score' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th>Gaps</th>
          </tr>
        </thead>
        <tbody>
          {filteredCases.map(c => (
            <tr key={c.id} onClick={() => onCaseSelect(c.id)} className="case-row">
              <td className="mono">{c.id}</td>
              <td className="mono">${c.amount.toFixed(2)}</td>
              <td>
                <span className={`badge ${c.decision}`}>{c.decision}</span>
              </td>
              <td>{c.confidence}</td>
              <td className="mono">{c.score}</td>
              <td>
                {c.has_gaps && <span className="gap-indicator">⚠</span>}
                {c.is_noise_case && <span className="noise-indicator" title="Label noise case">🔬</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default CaseList
