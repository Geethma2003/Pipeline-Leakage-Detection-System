import React, { useEffect, useState } from 'react';
import {
  ExperimentAnalysisResponse,
  ExperimentMetrics
} from '../../types';
import { api } from '../../services/api';
import {
  FlaskConical,
  Upload,
  Download,
  CheckCircle2,
  AlertTriangle,
  FileSpreadsheet,
  Activity
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid
} from 'recharts';

export const ExperimentComparisonView: React.FC = () => {
  const [data, setData] = useState<ExperimentAnalysisResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [customExperiments, setCustomExperiments] = useState<ExperimentMetrics[]>([]);

  useEffect(() => {
    loadDefaultExperiments();
  }, []);

  const loadDefaultExperiments = async () => {
    setLoading(true);
    try {
      const res = await api.getDefaultExperiments();
      setData(res);
    } catch (e: any) {
      setError(e.message || 'Failed to load experimental datasets');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const uploadedMetrics = await api.uploadExperimentCsv(file);
      setCustomExperiments(prev => [...prev, uploadedMetrics]);
    } catch (e: any) {
      alert(`Upload failed: ${e.message}`);
    }
  };

  const allSummaries = [...(data?.summaries || []), ...customExperiments];

  return (
    <div className="space-y-6">
      <div className="glass-card p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-cyan-500/15">
          <div>
            <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
              <FlaskConical className="w-5 h-5 text-cyan-400" />
              Experimental CSV Dataset Analysis & Comparison
            </h3>
            <p className="text-xs text-slate-400">
              Comparative vibration metrics across Normal, Pump Disturbance, and Confirmed Leak experiments
            </p>
          </div>

          <div className="flex items-center gap-2">
            <label className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 cursor-pointer flex items-center gap-1.5 transition">
              <Upload className="w-3.5 h-3.5" />
              Upload CSV Experiment
              <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
            </label>
          </div>
        </div>

        {/* Statistical Comparison Matrix Table */}
        <div className="space-y-2">
          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono">
            DSP & Statistical Summary Table (Matching analyze_experiments.py)
          </span>
          <div className="overflow-x-auto rounded-xl border border-cyan-500/20">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-navy-950 text-slate-400 uppercase text-[10px]">
                <tr>
                  <th className="p-3">Dataset Label</th>
                  <th className="p-3">Type Tag</th>
                  <th className="p-3">S1 RMS Median</th>
                  <th className="p-3">S1 RMS MAD</th>
                  <th className="p-3">S1 Abn %</th>
                  <th className="p-3">S1 Max Consec</th>
                  <th className="p-3">S2 RMS Median</th>
                  <th className="p-3">S2 RMS MAD</th>
                  <th className="p-3">S2 Abn %</th>
                  <th className="p-3">S2 Max Consec</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cyan-500/10 text-slate-200">
                {allSummaries.map((s, idx) => (
                  <tr key={idx} className="hover:bg-cyan-500/5 transition">
                    <td className="p-3 font-bold text-cyan-300">{s.label}</td>
                    <td className="p-3">
                      {s.is_simulated ? (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
                          SIMULATED
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold">
                          REAL LOGGED
                        </span>
                      )}
                    </td>
                    <td className="p-3 font-bold text-cyan-400">{s.s1_rms_median} ADC</td>
                    <td className="p-3">{s.s1_rms_mad}</td>
                    <td className={`p-3 font-bold ${s.s1_abn_pct > 50 ? 'text-red-400' : 'text-slate-200'}`}>{s.s1_abn_pct}%</td>
                    <td className="p-3">{s.s1_max_seq}s</td>
                    <td className="p-3 font-bold text-orange-400">{s.s2_rms_median} ADC</td>
                    <td className="p-3">{s.s2_rms_mad}</td>
                    <td className={`p-3 font-bold ${s.s2_abn_pct > 50 ? 'text-red-400' : 'text-slate-200'}`}>{s.s2_abn_pct}%</td>
                    <td className="p-3">{s.s2_max_seq}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Multi-Panel Time Series Comparison Plot */}
      {data?.datasets_preview && Object.keys(data.datasets_preview).length > 0 && (
        <div className="glass-card p-6 space-y-4">
          <h4 className="font-bold text-base text-slate-100 flex items-center gap-2 font-outfit">
            <Activity className="w-5 h-5 text-cyan-400" />
            Comparative Time-Series Curves (Sensor 1 RMS vs Time across Datasets)
          </h4>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Object.entries(data.datasets_preview).map(([filename, rows]) => (
              <div key={filename} className="bg-navy-950/70 p-4 rounded-xl border border-cyan-500/15 space-y-2">
                <span className="font-bold text-xs text-cyan-300 font-mono block">
                  Dataset: {filename}
                </span>
                <div className="h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={rows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="second_index" stroke="#64748b" tick={{ fontSize: 10 }} />
                      <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={{ backgroundColor: '#090d16', borderColor: 'rgba(56, 189, 248, 0.3)', fontSize: '11px' }} />
                      <Line type="monotone" dataKey="s1_rms" name="S1 RMS" stroke="#38bdf8" dot={false} strokeWidth={1.5} />
                      <Line type="monotone" dataKey="s2_rms" name="S2 RMS" stroke="#f97316" dot={false} strokeWidth={1.5} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
