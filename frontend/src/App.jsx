import React, { useState, useEffect } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart 
} from 'recharts';
import { Activity, Droplets, AlertTriangle, CheckCircle, Waves } from 'lucide-react';

const TOTAL_PIPELINE_LENGTH = 100; // units (e.g., meters)
const S1_POS = 10;
const S2_POS = 90;

const App = () => {
  const [data, setData] = useState([]);
  const [systemStatus, setSystemStatus] = useState('NORMAL');
  const [leakLocation, setLeakLocation] = useState(null); // distance from S1
  
  const [currentMetrics, setCurrentMetrics] = useState({
    s1Vibration: 12.0,
    s2Vibration: 11.5,
    flowRate: 150.0
  });

  // Simulation Logic
  useEffect(() => {
    let time = 0;
    const interval = setInterval(() => {
      time += 1;
      
      // Base normal values
      let s1 = 12.0 + (Math.random() * 2 - 1);
      let s2 = 11.5 + (Math.random() * 2 - 1);
      let flow = 150.0 + (Math.random() * 4 - 2);
      let status = 'NORMAL';
      let location = null;

      // Simulate event timeline
      const eventTime = time % 100;
      
      if (eventTime > 30 && eventTime < 45) {
        // Event 1: Pump Disturbance (Flow drops, NO abnormal vibration)
        flow = 120.0 + (Math.random() * 5);
        // vibrations stay relatively normal
      } 
      else if (eventTime > 60 && eventTime < 85) {
        // Event 2: LEAK! (Flow drops AND vibrations spike)
        flow = 115.0 + (Math.random() * 3);
        // Leak is closer to S1
        s1 = 85.0 + (Math.random() * 15);
        s2 = 35.0 + (Math.random() * 8);
        status = 'LEAK_DETECTED';
        
        // Simple mock calculation for distance based on amplitude ratio
        // In real life, cross-correlation of time-delay is used.
        const totalVib = s1 + s2;
        const s2Ratio = s1 / totalVib; // Higher s1 means closer to s1
        const calculatedDistance = (S2_POS - S1_POS) * (1 - s2Ratio); 
        location = Math.max(0, Math.min(calculatedDistance, S2_POS - S1_POS));
      }

      const newDataPoint = {
        time: time,
        s1Vibration: parseFloat(s1.toFixed(2)),
        s2Vibration: parseFloat(s2.toFixed(2)),
        flowRate: parseFloat(flow.toFixed(2)),
      };

      setCurrentMetrics(newDataPoint);
      setSystemStatus(status);
      setLeakLocation(location);

      setData(prev => {
        const newArr = [...prev, newDataPoint];
        if (newArr.length > 30) newArr.shift(); // keep last 30 seconds
        return newArr;
      });

    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const getStatusDisplay = () => {
    if (systemStatus === 'NORMAL') {
      return (
        <div className="status-badge status-normal">
          <CheckCircle size={18} /> System Normal
        </div>
      );
    }
    return (
      <div className="status-badge status-danger">
        <AlertTriangle size={18} /> Leak Detected
      </div>
    );
  };

  const getLeakPositionPercent = () => {
    if (leakLocation === null) return null;
    const absolutePos = S1_POS + leakLocation;
    return (absolutePos / TOTAL_PIPELINE_LENGTH) * 100;
  };

  return (
    <div className="dashboard-container">
      {/* HEADER */}
      <div className="header-section">
        <div>
          <h1>Pipeline Monitor</h1>
          <h2 className="brand-font">IoT Leakage Detection System</h2>
        </div>
        <div>{getStatusDisplay()}</div>
      </div>

      {/* LEFT COLUMN: Viz & Metrics */}
      <div className="main-content">
        <div className="glass-panel">
          <h2><Activity size={24} className="text-blue-500" /> Pipeline Status Visualization</h2>
          <p style={{color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1rem'}}>
            Linear pipeline segment with dual vibration sensors and central flow monitoring.
          </p>

          <div className="pipeline-viz">
            {/* Animated flow particles */}
            <div className="flow-particles">
              {[...Array(5)].map((_, i) => (
                <div 
                  key={i} 
                  className="particle" 
                  style={{ animationDelay: `${i * 0.8}s`, top: `${40 + Math.random()*20}%` }}
                />
              ))}
            </div>

            {/* S1 */}
            <div className="sensor-node" style={{ left: `${S1_POS}%`, position: 'absolute' }}>
              <div className="sensor-label">Vibration S1</div>
              <div className={`sensor-icon ${systemStatus === 'LEAK_DETECTED' ? 'active-vibration' : ''}`}>
                <Activity size={20} color={systemStatus === 'LEAK_DETECTED' ? '#ef4444' : '#3b82f6'} />
              </div>
            </div>

            {/* Flow Sensor */}
            <div className="sensor-node" style={{ left: '50%', position: 'absolute' }}>
              <div className="sensor-label">Flow Meter</div>
              <div className="sensor-icon flow">
                <Droplets size={20} color="#06b6d4" />
              </div>
            </div>

            {/* S2 */}
            <div className="sensor-node" style={{ left: `${S2_POS}%`, position: 'absolute' }}>
              <div className="sensor-label">Vibration S2</div>
              <div className={`sensor-icon ${systemStatus === 'LEAK_DETECTED' ? 'active-vibration' : ''}`}>
                <Activity size={20} color={systemStatus === 'LEAK_DETECTED' ? '#ef4444' : '#3b82f6'} />
              </div>
            </div>

            {/* Leak Indicator */}
            {systemStatus === 'LEAK_DETECTED' && leakLocation !== null && (
              <div className="leak-indicator" style={{ left: `${getLeakPositionPercent()}%` }}>
                <div className="leak-ripple"></div>
                <div className="leak-point"></div>
                <div className="leak-distance">
                  {leakLocation.toFixed(1)}m from S1
                </div>
              </div>
            )}
          </div>

          <div className="metrics-grid">
            <div className="metric-card">
              <div className="metric-label">Vibration S1 RMS</div>
              <div className={`metric-value ${currentMetrics.s1Vibration > 25 ? 'val-high' : 'val-normal'}`}>
                {currentMetrics.s1Vibration.toFixed(2)} <span className="metric-unit">g</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Vibration S2 RMS</div>
              <div className={`metric-value ${currentMetrics.s2Vibration > 25 ? 'val-high' : 'val-normal'}`}>
                {currentMetrics.s2Vibration.toFixed(2)} <span className="metric-unit">g</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Flow Rate</div>
              <div className={`metric-value ${currentMetrics.flowRate < 130 ? 'val-low' : 'val-normal'}`}>
                {currentMetrics.flowRate.toFixed(1)} <span className="metric-unit">L/min</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: Charts */}
      <div className="side-content glass-panel charts-container">
        <div>
          <h2><Activity size={20} /> Vibration Analysis</h2>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#f8fafc' }}
                />
                <Legend />
                <Line type="monotone" dataKey="s1Vibration" name="Sensor 1" stroke="#3b82f6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="s2Vibration" name="Sensor 2" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div style={{marginTop: '2rem'}}>
          <h2><Waves size={20} /> Flow Rate Monitoring</h2>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorFlow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} domain={[100, 180]} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                />
                <Legend />
                <Area type="monotone" dataKey="flowRate" name="Flow (L/min)" stroke="#06b6d4" fillOpacity={1} fill="url(#colorFlow)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;
