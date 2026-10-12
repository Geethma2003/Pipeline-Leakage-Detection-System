import React from 'react';
import { WindowDecision, BaselineProfile } from '../../types';
import { ShieldAlert, AlertTriangle, CheckCircle2, AlertOctagon, HelpCircle, Info } from 'lucide-react';

interface DetectionDecisionCardProps {
  decision: WindowDecision | null;
  baseline: BaselineProfile;
  currentWindowSec: number;
}

export const DetectionDecisionCard: React.FC<DetectionDecisionCardProps> = ({
  decision,
  baseline,
  currentWindowSec
}) => {
  const getDecisionBadge = (dec: string) => {
    if (dec.includes('SUSTAINED')) {
      return (
        <div className="p-4 rounded-xl bg-red-500/15 border-2 border-red-500/50 shadow-glow-red animate-pulse-glow flex items-center gap-3">
          <AlertOctagon className="w-8 h-8 text-red-500 shrink-0" />
          <div>
            <span className="font-extrabold text-base text-red-400 font-outfit uppercase tracking-wider block">
              SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK
            </span>
            <span className="text-xs text-slate-300">
              Multi-criteria persistence rule met (≥42/60 abnormal seconds). Vibration level elevated.
            </span>
          </div>
        </div>
      );
    } else if (dec.includes('TRANSIENT')) {
      return (
        <div className="p-4 rounded-xl bg-amber-500/15 border-2 border-amber-500/50 shadow-glow-amber flex items-center gap-3">
          <AlertTriangle className="w-8 h-8 text-amber-500 shrink-0" />
          <div>
            <span className="font-extrabold text-base text-amber-400 font-outfit uppercase tracking-wider block">
              TRANSIENT DISTURBANCE
            </span>
            <span className="text-xs text-slate-300">
              Impulse spike, pump speed change, or tapping noise without 60s sustained persistence.
            </span>
          </div>
        </div>
      );
    } else if (dec.includes('FAULT')) {
      return (
        <div className="p-4 rounded-xl bg-purple-500/15 border-2 border-purple-500/50 flex items-center gap-3">
          <AlertTriangle className="w-8 h-8 text-purple-400 shrink-0" />
          <div>
            <span className="font-extrabold text-base text-purple-400 font-outfit uppercase tracking-wider block">
              SENSOR OR CALIBRATION FAULT
            </span>
            <span className="text-xs text-slate-300">
              ADC rail voltage out of bounds or flatline signal detected.
            </span>
          </div>
        </div>
      );
    } else {
      return (
        <div className="p-4 rounded-xl bg-emerald-500/15 border-2 border-emerald-500/40 flex items-center gap-3">
          <CheckCircle2 className="w-8 h-8 text-emerald-400 shrink-0" />
          <div>
            <span className="font-extrabold text-base text-emerald-400 font-outfit uppercase tracking-wider block">
              NORMAL PIPELINE OPERATION
            </span>
            <span className="text-xs text-slate-300">
              Vibration levels within baseline statistical bounds across full 60s window.
            </span>
          </div>
        </div>
      );
    }
  };

  return (
    <div className="space-y-6">
      {/* 60-Second Final Decision Box */}
      <div className="glass-card p-6 relative overflow-hidden space-y-4">
        <div className="flex items-center justify-between border-b border-cyan-500/15 pb-3">
          <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
            <ShieldAlert className="w-5 h-5 text-cyan-400" />
            60-Second Multi-Criteria Decision Engine
          </h3>
          <span className="text-xs font-mono text-slate-400">
            Window #{decision?.window_index || 1}
          </span>
        </div>

        {decision ? getDecisionBadge(decision.decision) : (
          <div className="p-4 rounded-xl bg-navy-950 border border-slate-800 text-slate-400 text-xs text-center italic">
            Collecting first 60-second window samples ({currentWindowSec}/60s)...
          </div>
        )}

        {/* Reasoning Breakdown */}
        {decision && (
          <div className="p-4 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-2">
            <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider block font-mono">
              Decision Reasoning & Measurement Audit
            </span>
            <p className="text-xs text-slate-200 leading-relaxed font-sans">
              {decision.reasoning}
            </p>
          </div>
        )}

        {/* Baseline Comparison Matrix */}
        {decision && (
          <div className="space-y-2 pt-2">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono">
              Window Feature Audit vs Calibrated Baseline
            </span>
            <div className="overflow-x-auto rounded-xl border border-cyan-500/20">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-navy-950 text-slate-400 uppercase text-[10px]">
                  <tr>
                    <th className="p-2.5">Metric</th>
                    <th className="p-2.5">Sensor 1 (0.0m)</th>
                    <th className="p-2.5">Sensor 2 (2.0m)</th>
                    <th className="p-2.5">Threshold / Target</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-cyan-500/10 text-slate-200">
                  <tr>
                    <td className="p-2.5 text-slate-400">60s Window RMS Median</td>
                    <td className="p-2.5 font-bold text-cyan-400">{decision.s1_med_rms.toFixed(1)} ADC</td>
                    <td className="p-2.5 font-bold text-orange-400">{decision.s2_med_rms.toFixed(1)} ADC</td>
                    <td className="p-2.5 text-slate-400">S1: {baseline.s1_thresh.toFixed(1)}, S2: {baseline.s2_thresh.toFixed(1)}</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-slate-400">Abnormal Seconds Count</td>
                    <td className={`p-2.5 font-bold ${decision.s1_abnormal_count >= 42 ? 'text-red-400' : 'text-slate-200'}`}>
                      {decision.s1_abnormal_count} / 60s
                    </td>
                    <td className={`p-2.5 font-bold ${decision.s2_abnormal_count >= 42 ? 'text-red-400' : 'text-slate-200'}`}>
                      {decision.s2_abnormal_count} / 60s
                    </td>
                    <td className="p-2.5 text-slate-400">≥42 / 60s required (70%)</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-slate-400">Max Consecutive Run</td>
                    <td className="p-2.5">{decision.s1_max_seq} sec</td>
                    <td className="p-2.5">{decision.s2_max_seq} sec</td>
                    <td className="p-2.5 text-slate-400">≥15 consecutive sec</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-slate-400">Noise Variability (std/mean)</td>
                    <td className="p-2.5">{decision.s1_var_ratio.toFixed(2)}</td>
                    <td className="p-2.5">{decision.s2_var_ratio.toFixed(2)}</td>
                    <td className="p-2.5 text-slate-400">≤0.48 max ratio</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Honest Scientific Uncertainty Notice */}
      <div className="p-4 rounded-xl bg-navy-950/90 border border-amber-500/30 text-xs space-y-2">
        <div className="flex items-center gap-2 text-amber-400 font-bold uppercase tracking-wider">
          <Info className="w-4 h-4 shrink-0" />
          Honest Uncertainty & Scientific Notice
        </div>
        <p className="text-slate-300 leading-relaxed">
          Piezoelectric transducers record mechanical pipe wall vibrations. An anomaly classification indicates sustained acoustic vibration elevation above baseline. Vibration measurements alone cannot distinguish between micro-leakage and external contact without hydraulic flow/pressure validation.
        </p>
      </div>
    </div>
  );
};
