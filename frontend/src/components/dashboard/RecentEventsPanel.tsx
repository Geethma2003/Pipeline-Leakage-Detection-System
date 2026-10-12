import React, { useEffect, useState } from 'react';
import { History, AlertTriangle, ShieldCheck, FileText, ChevronRight } from 'lucide-react';
import { EventRecord } from '../../types';
import { api } from '../../services/api';

export const RecentEventsPanel: React.FC = () => {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);

  useEffect(() => {
    loadEvents();
  }, []);

  const loadEvents = async () => {
    try {
      const data = await api.getEvents(5);
      setEvents(data);
    } catch (e) {
      console.error('Failed to load recent events', e);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">CRITICAL</span>;
      case 'HIGH':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">HIGH</span>;
      case 'MEDIUM':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">MEDIUM</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500/20 text-slate-400 border border-slate-500/30">LOW</span>;
    }
  };

  return (
    <div className="glass-card p-5 relative overflow-hidden">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-cyan-500/15">
        <h4 className="font-semibold text-sm text-slate-100 flex items-center gap-2 font-outfit">
          <History className="w-4 h-4 text-cyan-400" />
          Recent Anomaly Log
        </h4>
        <button
          onClick={loadEvents}
          className="text-xs text-cyan-400 hover:text-cyan-300 transition font-medium"
        >
          Refresh
        </button>
      </div>

      <div className="space-y-2">
        {events.length === 0 ? (
          <div className="text-center py-6 text-slate-500 text-xs italic">
            No anomaly events logged yet. System running smoothly.
          </div>
        ) : (
          events.map((ev) => (
            <div
              key={ev.id}
              onClick={() => setSelectedEvent(ev)}
              className="p-3 rounded-lg bg-navy-950/70 border border-cyan-500/15 hover:border-cyan-500/30 transition cursor-pointer flex items-center justify-between text-xs"
            >
              <div className="space-y-1 pr-2">
                <div className="flex items-center gap-2">
                  {getSeverityBadge(ev.severity)}
                  <span className="font-semibold text-slate-200">{ev.status}</span>
                </div>
                <p className="text-[11px] text-slate-400 line-clamp-1">{ev.reasoning}</p>
                <div className="text-[10px] font-mono text-slate-500">
                  {new Date(ev.timestamp).toLocaleString()} | S1: {ev.s1_abnormal_sec}/60s, S2: {ev.s2_abnormal_sec}/60s
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 shrink-0" />
            </div>
          ))
        )}
      </div>

      {/* Selected Event Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 bg-navy-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-card p-6 max-w-lg w-full space-y-4 shadow-2xl border-cyan-500/30">
            <div className="flex items-center justify-between border-b border-cyan-500/20 pb-3">
              <h3 className="font-bold text-base text-cyan-300 flex items-center gap-2">
                <FileText className="w-5 h-5 text-cyan-400" />
                Event Detail #{selectedEvent.id}
              </h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2 p-2.5 rounded-lg bg-navy-950 border border-slate-800">
                <div>
                  <span className="text-slate-400 block font-mono">Timestamp</span>
                  <span className="font-semibold text-slate-200 font-mono">{new Date(selectedEvent.timestamp).toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-mono">Severity</span>
                  {getSeverityBadge(selectedEvent.severity)}
                </div>
              </div>

              <div>
                <span className="text-slate-400 block font-mono mb-1">Decision Reasoning</span>
                <p className="p-3 rounded-lg bg-navy-950 border border-slate-800 text-slate-200 leading-relaxed font-sans">
                  {selectedEvent.reasoning}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-slate-300 font-mono">
                <div className="p-2 bg-navy-950 rounded border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">Sensor 1 Median RMS</span>
                  <span className="font-bold text-cyan-400">{selectedEvent.s1_med_rms} ADC</span>
                </div>
                <div className="p-2 bg-navy-950 rounded border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">Sensor 2 Median RMS</span>
                  <span className="font-bold text-orange-400">{selectedEvent.s2_med_rms} ADC</span>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedEvent(null)}
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
