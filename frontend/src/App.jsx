import React, { useState } from 'react';
import { Upload, CheckCircle, Clock, TrendingUp } from 'lucide-react';

export default function App() {
  const API_HOST = import.meta.env.VITE_API_URL;
  const API_URL = API_HOST ? `https://${API_HOST}` : 'http://localhost:8080';
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState('idle'); 
  const [results, setResults] = useState([]); // Stores the calculated hands

  const handleUpload = async () => {
    if (!file) return;
    setStatus('uploading');
    setResults([]); // Clear previous results

    try {
      const formData = new FormData();
      formData.append('file', file);

      // 1. Upload File
      const response = await fetch(`${API_URL}/api/upload`, { method: 'POST', body: formData });
      const data = await response.json();

      if (!response.ok) throw new Error(data.error || 'Upload failed');

      // 2. Start Polling for Results
      setStatus('processing');
      pollResults(data.job_ids);

    } catch (error) {
      console.error(error);
      setStatus('error');
    }
  };

  // Helper: Check status of jobs every 2 seconds
  const pollResults = (jobIds) => {
    let completedCount = 0;
    
    const interval = setInterval(async () => {
      // For each job, check if we already have the result. If not, fetch it.
      const updates = await Promise.all(jobIds.map(async (id) => {
        const res = await fetch(`${API_URL}/api/results/${id}`);
        const json = await res.json();
        return json.status === 'completed' ? json.data : null;
      }));

      // Filter out nulls (pending jobs)
      const validResults = updates.filter(r => r !== null);
      setResults(validResults); // Update table

      // If all jobs are done, stop polling
      if (validResults.length === jobIds.length) {
        clearInterval(interval);
        setStatus('completed');
      }
    }, 2000);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '40px auto', fontFamily: 'sans-serif' }}>
      <h1>🃏 Poker Analysis Engine</h1>
      
      {/* Upload Box */}
      <div style={{ border: '2px dashed #ccc', padding: '30px', borderRadius: '8px', textAlign: 'center', marginBottom: '20px' }}>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} style={{ display: 'none' }} id="file-upload" />
        <label htmlFor="file-upload" style={{ cursor: 'pointer', display: 'block' }}>
          <Upload size={40} color="#007bff" />
          <p style={{ margin: '10px 0', color: '#666' }}>
            {file ? file.name : "Click to Upload PokerStars Log"}
          </p>
        </label>
        <button 
          onClick={handleUpload} 
          disabled={!file || status === 'uploading' || status === 'processing'}
          style={{ padding: '10px 20px', background: '#007bff', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          {status === 'processing' ? 'Processing...' : 'Analyze Hand History'}
        </button>
      </div>

      {/* Results Table */}
      {results.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '20px' }}>
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
              <tr key={idx} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px' }}>{r.hand_id}</td>
                <td style={{ padding: '10px', fontWeight: 'bold' }}>{r.hero_hand.join(' ')}</td>
                <td style={{ padding: '10px' }}>{r.board.join(' ')}</td>
                <td style={{ padding: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <TrendingUp size={16} color={r.equity > 50 ? 'green' : 'red'} />
                    {r.equity.toFixed(2)}%
                  </div>
                </td>
                <td style={{ padding: '10px' }}>
                  {r.equity > 50 ? 
                    <span style={{ color: 'green', fontWeight: 'bold' }}>Good Spot</span> : 
                    <span style={{ color: 'red', fontWeight: 'bold' }}>Mistake?</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}