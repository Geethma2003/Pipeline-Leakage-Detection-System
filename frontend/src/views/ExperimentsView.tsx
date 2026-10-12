import React from 'react';
import { ExperimentComparisonView } from '../components/experiments/ExperimentComparisonView';

export const ExperimentsView: React.FC = () => {
  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight">
          Experimental Dataset Analysis & Statistical Comparison
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Upload and compare experimental CSV files (Normal, Pump Disturbance, Confirmed Leakage) using Pandas DSP metrics
        </p>
      </div>

      <ExperimentComparisonView />
    </div>
  );
};
