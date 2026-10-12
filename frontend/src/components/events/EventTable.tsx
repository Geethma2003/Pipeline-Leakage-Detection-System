import React, { useState, useEffect } from 'react';
import { EventRecord } from '../../types';
import { api } from '../../services/api';
import { Search, Download, Filter, CheckCircle2, AlertTriangle, FileSpreadsheet, RefreshCw } from 'lucide-react';

export const EventTable: React.FC = () => {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedEventModal, setSelectedEventModal] = useState<EventRecord | null>(null);

  useEffect(() => {
    fetchEvents();
  }, [severityFilter]);

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const data = await api.getEvents(200, severityFilter === 'ALL' ? undefined : severityFilter);
      setEvents(data);
    } catch (e) {
      console.error('Failed to fetch events', e);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStatus = async (eventId: number, status: string) => {
    try {
      await api.updateEventStatus(eventId, status);
      fetchEvents();
      if (selectedEventModal?.id === eventId) {
        setSelectedEventModal(prev => prev ? { ...prev, operator_status: status as any } : null);
      }
    } catch (e) {
      console.error('Failed to update event operator status', e);
    }
  };

  const filtered = events.filter(e => {
    const term = search.toLowerCase();
    return (
      e.status.toLowerCase().includes(term) ||
      e.reasoning.toLowerCase().includes(term) ||
      e.severity.toLowerCase().includes(term) ||
      e.operator_status.toLowerCase().includes(term)
    );
  });

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'CRITICAL':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">CRITICAL</span>;
      case 'HIGH':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">HIGH</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">MEDIUM</span>;
    }
  };

  return (
    <div className="glass-card p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-cyan-500/15">
        <div>
          <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
            <FileSpreadsheet className="w-5 h-5 text-cyan-400" />
            Historical Anomaly & Alert Log (SQLite Database)
          </h3>
          <p className="text-xs text-slate-400">
            Searchable log of past 60-second window anomaly decisions with operator confirmation workflows
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchEvents}
            className="p-2 rounded-lg bg-navy-950 text-slate-300 hover:text-white border border-cyan-500/20 transition"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
          <button
            onClick={() => api.exportEventsCsv()}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 flex items-center gap-1.5 transition"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Filter and Search Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search events by reasoning, status..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-navy-950 border border-cyan-500/20 rounded-lg pl-9 pr-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="text-slate-400 font-mono">Severity:</span>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-navy-950 border border-cyan-500/20 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 font-mono"
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
          </select>
        </div>
      </div>

      {/* Events Table */}
      <div className="overflow-x-auto rounded-xl border border-cyan-500/20">
        <table className="w-full text-left text-xs">
          <thead className="bg-navy-950 text-slate-400 font-mono text-[10px] uppercase border-b border-cyan-500/20">
            <tr>
              <th className="p-3">ID</th>
              <th className="p-3">Timestamp</th>
              <th className="p-3">Status</th>
              <th className="p-3">Severity</th>
              <th className="p-3">S1 / S2 Abnormal</th>
              <th className="p-3">Operator Action</th>
              <th className="p-3 text-right">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cyan-500/10 text-slate-200 font-sans">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-slate-500 italic">
                  No historical event records match the search filter.
                </td>
              </tr>
            ) : (
              filtered.map((ev) => (
                <tr key={ev.id} className="hover:bg-cyan-500/5 transition">
                  <td className="p-3 font-mono font-bold text-slate-400">#{ev.id}</td>
                  <td className="p-3 font-mono text-slate-300">
                    {new Date(ev.timestamp).toLocaleString()}
                  </td>
                  <td className="p-3 font-semibold text-cyan-300">{ev.status}</td>
                  <td className="p-3">{getSeverityBadge(ev.severity)}</td>
                  <td className="p-3 font-mono">
                    <span className="text-cyan-400">{ev.s1_abnormal_sec}/60s</span> /{' '}
                    <span className="text-orange-400">{ev.s2_abnormal_sec}/60s</span>
                  </td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                      ev.operator_status === 'CONFIRMED_LEAK'
                        ? 'bg-red-500/20 text-red-300 border border-red-500/30'
                        : ev.operator_status === 'FALSE_ALARM'
                        ? 'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    }`}>
                      {ev.operator_status}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <button
                      onClick={() => setSelectedEventModal(ev)}
                      className="px-2.5 py-1 rounded bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 border border-cyan-500/30 font-medium"
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal Detail & Confirmation Drawer */}
      {selectedEventModal && (
        <div className="fixed inset-0 z-50 bg-navy-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-card p-6 max-w-lg w-full space-y-4 shadow-2xl border-cyan-500/30">
            <div className="flex items-center justify-between border-b border-cyan-500/20 pb-3">
              <h3 className="font-bold text-base text-cyan-300">
                Event Log Details #{selectedEventModal.id}
              </h3>
              <button
                onClick={() => setSelectedEventModal(null)}
                className="text-slate-400 hover:text-white font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-lg bg-navy-950 border border-slate-800 space-y-1 font-mono">
                <div><span className="text-slate-400">Timestamp:</span> {new Date(selectedEventModal.timestamp).toLocaleString()}</div>
                <div><span className="text-slate-400">Decision Status:</span> <span className="font-bold text-cyan-300">{selectedEventModal.status}</span></div>
                <div><span className="text-slate-400">Reasoning:</span> {selectedEventModal.reasoning}</div>
              </div>

              {/* Operator Action Buttons */}
              <div className="space-y-2 pt-2">
                <span className="font-bold text-slate-300 block font-mono">Operator Verification Action:</span>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleUpdateStatus(selectedEventModal.id, 'ACKNOWLEDGED')}
                    className="px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40 text-xs font-semibold"
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => handleUpdateStatus(selectedEventModal.id, 'CONFIRMED_LEAK')}
                    className="px-3 py-1.5 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/40 text-xs font-semibold"
                  >
                    Confirm Leak
                  </button>
                  <button
                    onClick={() => handleUpdateStatus(selectedEventModal.id, 'FALSE_ALARM')}
                    className="px-3 py-1.5 rounded-lg bg-slate-500/20 text-slate-300 hover:bg-slate-500/30 border border-slate-500/40 text-xs font-semibold"
                  >
                    Mark False Alarm
                  </button>
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedEventModal(null)}
                className="px-4 py-2 rounded-lg bg-navy-950 text-slate-300 border border-slate-800"
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
