import React from 'react';
import { EventTable } from '../components/events/EventTable';

export const HistoryView: React.FC = () => {
  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight">
          Historical Event Log & Operator Verification
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Searchable event history stored in SQLite database with operator confirmation, filtering, and CSV export
        </p>
      </div>

      <EventTable />
    </div>
  );
};
