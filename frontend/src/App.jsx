import React, { useState, useEffect } from 'react';
import { Upload, TrendingUp, TrendingDown } from 'lucide-react';

// Use window.io provided by the CDN script in index.html
const io = window.io;

// Determine API URL based on environment (Cloud or Local)
const API_HOST = import.meta.env.VITE_API_URL;
const API_URL = API_HOST ? `https://${API_HOST}` : 'http://localhost:8080';

// Initialize SocketIO connection
const socket = io(API_URL, {
  reconnectionAttempts: 5,
  transports: ['websocket', 'polling'],
  upgrade: false,
  secure: false
});

export default function App() {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState('idle');
  const [results, setResults] = useState([]); 
  const [historicalResults, setHistoricalResults] = useState([]); 
  const [historyUpdateCount, setHistoryUpdateCount] = useState(0); // Dedicated Trigger State

  // Function to fetch data (does NOT set state)
  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/api/history`);
      const data = await response.json();
      
      if (response.ok && data.status === 'success') {
        // Return the raw data array
        return data.history; 
      }
      return [];
    } catch (error) {
      console.error("Failed to fetch history:", error);
      return [];
    }
  };

  // 1. Effect to manage state synchronization based on the external trigger
  useEffect(() => {
    // This function executes the fetch and sets the historical state
    const loadHistory = async () => {
      const history = await fetchHistory();
      setHistoricalResults(history);
    };

    // Run this function whenever the component mounts OR the counter changes
    loadHistory();
    
  }, [historyUpdateCount]); // CRITICAL: This runs the fetch and updates the table instantly when the counter changes.

  // 2. Effect to set up sockets (runs only once on mount)
  useEffect(() => {
    
    socket.on('connect', () => {
        console.log("Connected to Real-time Stream");
    });

    socket.on('job_complete', (data) => {
        console.log("Received real-time result for:", data.job_id);
        
        // A. Update Real-time view (Instant)
        setResults(prev => [...prev, data.data]);
        
        // B. Trigger the History Update: This increments the counter, which forces the first useEffect block to run.
        setHistoryUpdateCount(prev => prev + 1); 
    });

    return () => {
        socket.off('job_complete');
        socket.off('connect');
    };
  }, []); // Empty dependency array (Runs only once on mount to set up listeners)

  const handleUpload = async () => {
    if (!file) return;
    setStatus('uploading');
    setResults([]); 

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/api/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.error || 'Upload failed');

      setStatus('processing');

    } catch (error) {
      console.error(error);
      setStatus('error');
    }
  };
  
  const renderVerdict = (equity) => {
    if (equity > 50) return <span style={{ color: 'green', fontWeight: 'bold' }}>Advantage</span>;
    if (equity > 30) return <span style={{ color: 'orange', fontWeight: 'bold' }}>Marginal</span>;
    return <span style={{ color: 'red', fontWeight: 'bold' }}>Mistake?</span>;
  }

  const renderEquityCell = (equity) => {
    const isGood = equity > 50;
    const Icon = isGood ? TrendingUp : TrendingDown;
    const color = isGood ? 'green' : 'red';
    
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <Icon size={16} color={color} />
        {equity.toFixed(2)}%
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '900px', margin: '40px auto', fontFamily: 'sans-serif' }}>
      <h1>🃏 Poker Analysis Engine</h1>
      
      {/* Upload Section */}
      <div style={{ border: '2px dashed #ccc', padding: '30px', borderRadius: '8px', textAlign: 'center', marginBottom: '40px' }}>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} style={{ display: 'none' }} id="file-upload" />
        <label htmlFor="file-upload" style={{ cursor: 'pointer', display: 'block' }}>
          <Upload size={40} color="#007bff" />
          <p style={{ margin: '10px 0', color: '#666' }}>
            {file ? file.name : "Click to Upload PokerStars Log (.txt)"}
          </p>
        </label>
        <button 
          onClick={handleUpload} 
          disabled={!file || status === 'uploading' || status === 'processing'}
          style={{ padding: '10px 20px', background: status === 'processing' ? '#00b3ff' : '#007bff', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          {status === 'processing' ? 'Processing Jobs Instantly...' : 'Analyze Hand History'}
        </button>
      </div>

      {/* Real-time Results */}
      {results.length > 0 && (
        <>
          <h2>✨ Current Analysis ({results.length} Jobs Done)</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '10px' }}>
            <thead>
              <tr style={{ background: '#f4f4f4', textAlign: 'left' }}>
                <th style={{ padding: '10px' }}>Hand ID</th>
                <th style={{ padding: '10px' }}>My Hand</th>
                <th style={{ padding: '10px' }}>Board</th>
                <th style={{ padding: '10px' }}>Equity</th>
                <th style={{ padding: '10px' }}>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid #e0e0e0' }}>
                  <td style={{ padding: '10px' }}>{r.hand_id}</td>
                  <td style={{ padding: '10px', fontWeight: 'bold' }}>{r.hero_hand.join(' ')}</td>
                  <td style={{ padding: '10px' }}>{r.board.join(' ')}</td>
                  <td style={{ padding: '10px' }}>{renderEquityCell(r.equity)}</td>
                  <td style={{ padding: '10px' }}>{renderVerdict(r.equity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {/* Historical Data */}
      <div style={{ marginTop: '50px' }}>
        <h2>📚 Historical Data ({historicalResults.length} Hands Total)</h2>
        {historicalResults.length === 0 ? (
          <p style={{ color: '#888' }}>No permanent history found. Upload a log!</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '10px' }}>
            <thead>
              <tr style={{ background: '#e0e0e0', textAlign: 'left' }}>
                <th style={{ padding: '10px' }}>Hand ID</th>
                <th style={{ padding: '10px' }}>My Hand</th>
                <th style={{ padding: '10px' }}>Board</th>
                <th style={{ padding: '10px' }}>Equity</th>
                <th style={{ padding: '10px' }}>Processed</th>
              </tr>
            </thead>
            <tbody>
              {historicalResults.map((h, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid #ccc' }}>
                  <td style={{ padding: '10px' }}>{h.hand_id}</td>
                  <td style={{ padding: '10px', fontWeight: 'bold' }}>{h.hero_hand.replace(/,/g, ' ')}</td>
                  <td style={{ padding: '10px' }}>{h.board.replace(/,/g, ' ')}</td>
                  <td style={{ padding: '10px' }}>{renderEquityCell(h.equity)}</td>
                  <td style={{ padding: '10px' }}>{new Date(h.processed_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}