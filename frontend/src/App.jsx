import { useState } from 'react'
import './App.css'
import CaseList from './components/CaseList'
import CaseDetail from './components/CaseDetail'
import MetricsView from './components/MetricsView'

function App() {
  const [view, setView] = useState('list') // 'list', 'detail', 'metrics'
  const [selectedCaseId, setSelectedCaseId] = useState(null)

  const handleCaseSelect = (caseId) => {
    setSelectedCaseId(caseId)
    setView('detail')
  }

  const handleBack = () => {
    setView('list')
    setSelectedCaseId(null)
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>DisputeLens</h1>
        <nav>
          <button 
            className={view === 'list' ? 'active' : ''} 
            onClick={() => setView('list')}
          >
            Cases
          </button>
          <button 
            className={view === 'metrics' ? 'active' : ''} 
            onClick={() => setView('metrics')}
          >
            Metrics
          </button>
        </nav>
      </header>

      <main className="app-main">
        {view === 'list' && <CaseList onCaseSelect={handleCaseSelect} />}
        {view === 'detail' && <CaseDetail caseId={selectedCaseId} onBack={handleBack} />}
        {view === 'metrics' && <MetricsView />}
      </main>
    </div>
  )
}

export default App
