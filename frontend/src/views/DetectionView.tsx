import React from 'react';
import { useTelemetry } from '../context/TelemetryContext';
import { DetectionDecisionCard } from '../components/detection/DetectionDecisionCard';

export const DetectionView: React.FC = () => {
  const { latestDecision, baseline, currentWindowSec } = useTelemetry();

  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight">
          60-Second Leak Detection & Multi-Criteria Workflow
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Detailed evaluation of per-second abnormal duration, persistence thresholds, and decision reasoning
        </p>
      </div>

      <DetectionDecisionCard
        decision={latestDecision}
        baseline={baseline}
        currentWindowSec={currentWindowSec}
      />
    </div>
  );
};
