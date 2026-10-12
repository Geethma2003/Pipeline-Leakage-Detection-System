import React from 'react';
import { useTelemetry } from '../context/TelemetryContext';
import { PipelineDiagramSvg } from '../components/pipeline/PipelineDiagramSvg';
import { HighResolutionLocalizationCard } from '../components/pipeline/HighResolutionLocalizationCard';
import { LiveGpsMap } from '../components/pipeline/LiveGpsMap';

export const PipelineView: React.FC = () => {
  const { latestTelemetry, baseline, latestDecision, systemState } = useTelemetry();

  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight">
          Interactive Pipeline Schematic & Sensor Location
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          2.0-meter steel water pipeline schematic with acoustic wave animations, high-speed TDOA leak localization & live GPS map
        </p>
      </div>

      <HighResolutionLocalizationCard />

      <PipelineDiagramSvg
        latest={latestTelemetry}
        baseline={baseline}
        decision={latestDecision}
        systemState={systemState}
      />

      <LiveGpsMap />
    </div>
  );
};


