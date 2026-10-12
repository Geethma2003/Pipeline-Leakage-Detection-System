import React, { useState } from 'react';
import { TelemetryRecord, BaselineProfile, WindowDecision } from '../../types';
import { useTelemetry } from '../../context/TelemetryContext';
import { Activity, ShieldAlert, AlertTriangle, Droplets, Info, CheckCircle2, Lock, Unlock } from 'lucide-react';

interface PipelineDiagramProps {
  latest: TelemetryRecord | null;
  baseline: BaselineProfile;
  decision: WindowDecision | null;
  systemState: string;
}

export const PipelineDiagramSvg: React.FC<PipelineDiagramProps> = ({
  latest,
  baseline,
  decision,
  systemState
}) => {
  const { flow } = useTelemetry();
  const [selectedSensorModal, setSelectedSensorModal] = useState<'s1' | 's2' | null>(null);

  const flowConfirmed = flow?.leak_confirmed ?? false;
  const flowProgress = flow?.leak_progress ?? 0;
  const flowIn = flow?.flow_in_lpm ?? 0.0;
  const flowOut = flow?.flow_out_lpm ?? 0.0;
  const isConfirmedLeak = flowConfirmed || systemState === 'CONFIRMED_LEAK';

  const isAnomaly = isConfirmedLeak || (decision && decision.decision.includes('SUSTAINED'));
  const isTransient = decision && decision.decision.includes('TRANSIENT');

  const s1Rms = latest?.s1_rms ?? 12.0;
  const s2Rms = latest?.s2_rms ?? 11.5;

  const locValid = decision?.loc_valid ?? false;
  const estimatedDistanceM = decision?.estimated_distance_m;

  // CRITICAL RULE: Official location is ONLY revealed when flow confirmed!
  const isLocationRevealed = isConfirmedLeak && locValid && estimatedDistanceM !== undefined && estimatedDistanceM !== null;

  // Calculate leak position on 2.0m SVG scale (from x=160 to x=640 in SVG coordinates)
  // Sensor 1 @ x=160 (0.0m), Sensor 2 @ x=640 (2.0m), total width = 480px (240px/meter)
  const leakX = (isLocationRevealed && estimatedDistanceM !== undefined && estimatedDistanceM !== null)
    ? 160 + (Math.max(0, Math.min(2.0, estimatedDistanceM)) / 2.0) * 480
    : null;

  return (
    <div className="glass-card p-6 relative overflow-hidden space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-cyan-500/15">
        <div>
          <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
            <Droplets className="w-5 h-5 text-cyan-400" />
            2.0-Meter Steel Water Pipeline Schematic
          </h3>
          <p className="text-xs text-slate-400">
            Interactive physical representation with piezoelectric vibration sensors @ 0.0m and 2.0m
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-bold border uppercase tracking-wide flex items-center gap-1.5 ${
            isAnomaly
              ? 'bg-red-500/20 text-red-400 border-red-500/50 animate-pulse shadow-glow-red'
              : isTransient
              ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
              : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isAnomaly ? 'bg-red-500 animate-ping' : 'bg-emerald-400'}`} />
            {systemState}
          </span>
        </div>
      </div>

      {/* Main SVG Pipeline Canvas */}
      <div className="relative w-full bg-navy-950/90 rounded-2xl p-4 border border-cyan-500/20 overflow-x-auto shadow-inner">
        <svg
          viewBox="0 0 800 240"
          className="w-full h-auto min-w-[650px] overflow-visible"
        >
          <defs>
            {/* Gradient for Pipe Exterior */}
            <linearGradient id="steelPipeGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#334155" />
              <stop offset="30%" stopColor="#64748b" />
              <stop offset="70%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>

            {/* Normal Water Flow Gradient */}
            <linearGradient id="waterNormalGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.8" />
              <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#0891b2" stopOpacity="0.8" />
            </linearGradient>

            {/* Anomaly Fluid Flow Gradient */}
            <linearGradient id="waterAnomalyGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.8" />
              <stop offset="40%" stopColor="#ef4444" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#0891b2" stopOpacity="0.8" />
            </linearGradient>
          </defs>

          {/* Grid lines background */}
          <line x1="160" y1="20" x2="160" y2="200" stroke="rgba(56, 189, 248, 0.15)" strokeDasharray="3 3" />
          <line x1="640" y1="20" x2="640" y2="200" stroke="rgba(56, 189, 248, 0.15)" strokeDasharray="3 3" />

          {/* Scale labels */}
          <text x="160" y="215" fill="#9467bb" fontSize="11" textAnchor="middle" fontFamily="monospace">Sensor 1 (0.0 m)</text>
          <text x="400" y="215" fill="#64748b" fontSize="11" textAnchor="middle" fontFamily="monospace">Pipeline Distance: 2.0 Meters</text>
          <text x="640" y="215" fill="#9467bb" fontSize="11" textAnchor="middle" fontFamily="monospace">Sensor 2 (2.0 m)</text>

          {/* Water Pump Unit (Left Inlet) */}
          <g transform="translate(40, 70)">
            <rect x="0" y="0" width="70" height="80" rx="10" fill="#1e293b" stroke="#38bdf8" strokeWidth="2" />
            <circle cx="35" cy="40" r="22" fill="#0f172a" stroke="#38bdf8" strokeWidth="2" />
            {/* Animated Impeller blades */}
            <g transform="translate(35, 40)" className="animate-spin origin-center duration-1000">
              <line x1="-15" y1="0" x2="15" y2="0" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" />
              <line x1="0" y1="-15" x2="0" y2="15" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" />
            </g>
            <text x="35" y="-10" fill="#9467bb" fontSize="11" fontWeight="bold" textAnchor="middle">Water Pump</text>
          </g>

          {/* Inlet pipe from pump to main pipe */}
          <rect x="110" y="95" width="50" height="30" fill="url(#steelPipeGrad)" stroke="#475569" strokeWidth="1" />
          <rect x="110" y="100" width="50" height="20" fill="url(#waterNormalGrad)" />

          {/* Outer Steel Pipe Body */}
          <rect x="160" y="80" width="480" height="60" rx="8" fill="url(#steelPipeGrad)" stroke="#475569" strokeWidth="2" />

          {/* Inner Fluid Chamber */}
          <rect
            x="160"
            y="90"
            width="480"
            height="40"
            rx="4"
            fill={isAnomaly ? "url(#waterAnomalyGrad)" : "url(#waterNormalGrad)"}
          />

          {/* Animated Water Flow Dashed Overlay */}
          <line
            x1="160"
            y1="110"
            x2="640"
            y2="110"
            stroke="#ffffff"
            strokeWidth="3"
            strokeDasharray="12 16"
            className="animate-water-flow opacity-60"
          />

          {/* Flow Direction Arrows */}
          <path d="M 280 110 L 300 102 L 300 118 Z" fill="#ffffff" opacity="0.7" />
          <path d="M 500 110 L 520 102 L 520 118 Z" fill="#ffffff" opacity="0.7" />

          {/* SENSOR 1 NODE (0.0 m) */}
          <g
            transform="translate(160, 80)"
            onClick={() => setSelectedSensorModal('s1')}
            className="cursor-pointer group"
          >
            {/* Piezo Mounting Block */}
            <rect x="-18" y="-30" width="36" height="30" rx="4" fill="#0f172a" stroke="#38bdf8" strokeWidth="2" />
            <circle cx="0" cy="-15" r="8" fill={latest?.s1_abnormal ? "#ef4444" : "#38bdf8"} className="animate-pulse" />

            {/* Acoustic Waves Animation on Anomaly */}
            {latest?.s1_abnormal === 1 && (
              <circle cx="0" cy="0" r="30" fill="none" stroke="#ef4444" strokeWidth="2" className="animate-ping" opacity="0.7" />
            )}

            <text x="0" y="-40" fill="#38bdf8" fontSize="12" fontWeight="bold" textAnchor="middle" className="group-hover:fill-cyan-300">
              Sensor 1 (0.0m)
            </text>
            <text x="0" y="80" fill="#9467bb" fontSize="11" fontFamily="monospace" textAnchor="middle">
              {s1Rms.toFixed(1)} ADC
            </text>
          </g>

          {/* SENSOR 2 NODE (2.0 m) */}
          <g
            transform="translate(640, 80)"
            onClick={() => setSelectedSensorModal('s2')}
            className="cursor-pointer group"
          >
            {/* Piezo Mounting Block */}
            <rect x="-18" y="-30" width="36" height="30" rx="4" fill="#0f172a" stroke="#f97316" strokeWidth="2" />
            <circle cx="0" cy="-15" r="8" fill={latest?.s2_abnormal ? "#ef4444" : "#f97316"} className="animate-pulse" />

            {/* Acoustic Waves Animation on Anomaly */}
            {latest?.s2_abnormal === 1 && (
              <circle cx="0" cy="0" r="30" fill="none" stroke="#ef4444" strokeWidth="2" className="animate-ping" opacity="0.7" />
            )}

            <text x="0" y="-40" fill="#f97316" fontSize="12" fontWeight="bold" textAnchor="middle" className="group-hover:fill-orange-300">
              Sensor 2 (2.0m)
            </text>
            <text x="0" y="80" fill="#9467bb" fontSize="11" fontFamily="monospace" textAnchor="middle">
              {s2Rms.toFixed(1)} ADC
            </text>
          </g>

          {/* INLET FLOW METER (YF-S201, D2) */}
          <g transform="translate(135, 78)">
            <rect x="-14" y="-22" width="28" height="22" rx="4" fill="#0f172a" stroke="#06b6d4" strokeWidth="1.5" />
            <circle cx="0" cy="-11" r="5" fill="#06b6d4" className="animate-spin origin-center duration-1000" />
            <text x="0" y="-28" fill="#06b6d4" fontSize="10" fontWeight="bold" textAnchor="middle">
              Flow In
            </text>
            <text x="0" y="60" fill="#06b6d4" fontSize="9" fontFamily="monospace" textAnchor="middle">
              {flowIn.toFixed(2)} L/m
            </text>
            <text x="0" y="70" fill="#64748b" fontSize="8" fontFamily="monospace" textAnchor="middle">
              Inlet — D2
            </text>
          </g>

          {/* OUTLET FLOW METER (YF-S201, D3) */}
          <g transform="translate(665, 78)">
            <rect x="-14" y="-22" width="28" height="22" rx="4" fill="#0f172a" stroke="#f97316" strokeWidth="1.5" />
            <circle cx="0" cy="-11" r="5" fill="#f97316" className="animate-spin origin-center duration-1000" />
            <text x="0" y="-28" fill="#f97316" fontSize="10" fontWeight="bold" textAnchor="middle">
              Flow Out
            </text>
            <text x="0" y="60" fill="#f97316" fontSize="9" fontFamily="monospace" textAnchor="middle">
              {flowOut.toFixed(2)} L/m
            </text>
            <text x="0" y="70" fill="#64748b" fontSize="8" fontFamily="monospace" textAnchor="middle">
              Outlet — D3
            </text>
          </g>

          {/* LEAK ANOMALY INDICATOR */}
          {isLocationRevealed && leakX !== null ? (
            <g transform={`translate(${leakX}, 110)`}>
              <circle cx="0" cy="0" r="24" fill="rgba(239, 68, 68, 0.3)" className="animate-ping" />
              <circle cx="0" cy="0" r="14" fill="#ef4444" stroke="#ffffff" strokeWidth="2" />
              <text x="0" y="32" fill="#ef4444" fontSize="11" fontWeight="bold" textAnchor="middle">
                Confirmed Leak @ {estimatedDistanceM?.toFixed(2)}m
              </text>
            </g>
          ) : isConfirmedLeak ? (
            <g transform="translate(400, 110)">
              <rect x="-185" y="-14" width="370" height="28" rx="6" fill="#0f172a" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x="0" y="4" fill="#f59e0b" fontSize="11" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                ⚠️ Leak Confirmed by Flow — Acoustic Location Unavailable
              </text>
            </g>
          ) : isAnomaly ? (
            <g transform="translate(400, 110)">
              <rect x="-140" y="-14" width="280" height="28" rx="6" fill="#0f172a" stroke="#64748b" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x="0" y="4" fill="#94a3b8" fontSize="11" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                🔒 Location Concealed — Normal Flow
              </text>
            </g>
          ) : null}
        </svg>
      </div>

      {/* Localization Status Box */}
      <div className={`p-4 rounded-xl border flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs ${
        isLocationRevealed
          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          : isAnomaly
          ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
          : 'bg-navy-950/80 border-slate-800 text-slate-300'
      }`}>
        <div className="flex items-center gap-3">
          {isLocationRevealed ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          ) : flowConfirmed ? (
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          ) : (
            <Info className="w-5 h-5 text-amber-400 shrink-0" />
          )}
          <div>
            <span className="font-bold block text-sm">
              {isLocationRevealed
                ? `Flow Verified & Acoustically Localized: ~${estimatedDistanceM} meters from Sensor 1`
                : flowConfirmed
                ? 'Leak Confirmed by Flow Meters — Acoustic Location Unavailable'
                : 'Leak Location Concealed — Awaiting Dual Flow Meter Confirmation'}
            </span>
            <span className="text-[11px] text-slate-400">
              {isLocationRevealed
                ? `Cross-correlation peak coefficient R = ${decision?.peak_corr.toFixed(2)} (Min required: 0.65). Verified across 3 consecutive flow windows.`
                : flowConfirmed
                ? 'Persistent flow imbalance >= 0.10 L/min confirmed leakage. Acoustic correlation is below 0.65; location is suppressed to avoid false coordinates.'
                : `Dual YF-S201 flow sensors have not completed 3-window leak confirmation (${flowProgress}/3). Vibration location is concealed per AquaGuard AI rule.`}
            </span>
          </div>
        </div>

        <div className="font-mono text-[11px] bg-navy-950 px-3 py-1.5 rounded-lg border border-slate-800 shrink-0 flex items-center gap-2">
          <span>Flow Confirmed:</span>
          <span className={`font-bold ${flowConfirmed ? 'text-red-400' : 'text-emerald-400'}`}>
            {flowConfirmed ? 'YES (ALARM 0x08)' : 'NO (BALANCED)'}
          </span>
        </div>
      </div>

      {/* Sensor Modal */}
      {selectedSensorModal && (
        <div className="fixed inset-0 z-50 bg-navy-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-card p-6 max-w-md w-full space-y-4 shadow-2xl border-cyan-500/30">
            <div className="flex items-center justify-between border-b border-cyan-500/20 pb-3">
              <h3 className="font-bold text-base text-cyan-300 flex items-center gap-2 font-outfit">
                <Activity className="w-5 h-5 text-cyan-400" />
                {selectedSensorModal === 's1' ? 'Piezo Sensor 1 Details (A0)' : 'Piezo Sensor 2 Details (A1)'}
              </h3>
              <button
                onClick={() => setSelectedSensorModal(null)}
                className="text-slate-400 hover:text-white font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="p-3 bg-navy-950 rounded-lg border border-slate-800 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-400">Position on Pipe:</span>
                  <span className="text-slate-200 font-bold">{selectedSensorModal === 's1' ? '0.0 Meters' : '2.0 Meters'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Live RMS Amplitude:</span>
                  <span className="text-cyan-400 font-bold">
                    {(selectedSensorModal === 's1' ? latest?.s1_rms : latest?.s2_rms)?.toFixed(2)} ADC
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Baseline Threshold:</span>
                  <span className="text-amber-400 font-bold">
                    {(selectedSensorModal === 's1' ? baseline.s1_thresh : baseline.s2_thresh)?.toFixed(2)} ADC
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Peak-to-Peak (P2P):</span>
                  <span className="text-slate-200">
                    {(selectedSensorModal === 's1' ? latest?.s1_p2p : latest?.s2_p2p)?.toFixed(1)} ADC
                  </span>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setSelectedSensorModal(null)}
                className="px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
