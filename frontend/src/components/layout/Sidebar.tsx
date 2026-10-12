import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  LineChart,
  Pipette as PipeIcon,
  ShieldAlert,
  History,
  FlaskConical,
  Settings,
  Cpu,
  CheckCircle2,
  AlertTriangle
} from 'lucide-react';
import { useTelemetry } from '../../context/TelemetryContext';

interface SidebarProps {
  mobileMenuOpen: boolean;
  setMobileMenuOpen: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ mobileMenuOpen, setMobileMenuOpen }) => {
  const { diagnostics, systemState } = useTelemetry();

  const navItems = [
    { path: '/', label: 'Overview Dashboard', icon: LayoutDashboard },
    { path: '/analytics', label: 'Live Sensor Analytics', icon: LineChart },
    { path: '/pipeline', label: 'Interactive Pipeline', icon: PipeIcon },
    { path: '/detection', label: '60s Leak Detection', icon: ShieldAlert },
    { path: '/history', label: 'Historical Events', icon: History },
    { path: '/experiments', label: 'Experimental Analysis', icon: FlaskConical },
    { path: '/settings', label: 'Settings & Hardware', icon: Settings },
  ];

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-navy-950/80 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside
        className={`fixed top-16 bottom-0 left-0 z-40 w-64 bg-navy-900/95 backdrop-blur-md border-r border-cyan-500/15 flex flex-col justify-between transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-4 space-y-6 overflow-y-auto">
          {/* Hardware Quick Status Card */}
          <div className="p-3 rounded-xl bg-navy-950/80 border border-cyan-500/20 text-xs space-y-2">
            <div className="flex items-center justify-between text-slate-300 font-semibold border-b border-cyan-500/10 pb-1.5">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <Cpu className="w-4 h-4" /> Hardware Status
              </span>
              <span className="font-mono text-[10px] text-slate-400">2.0m Pipe</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-400">Serial Port:</span>
              <span className="font-mono font-medium text-slate-200">{diagnostics?.serial_port || 'COM3'}</span>
            </div>
            <div className="flex justify-between items-center text-[11px]">
              <span className="text-slate-400">State:</span>
              <span className={`font-semibold text-[10px] uppercase px-2 py-0.5 rounded ${
                systemState === 'NORMAL' ? 'bg-emerald-500/20 text-emerald-400' :
                systemState === 'CONFIRMED_LEAK' ? 'bg-red-500/20 text-red-400 animate-pulse' :
                'bg-amber-500/20 text-amber-400'
              }`}>
                {systemState}
              </span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1">
            <div className="px-3 pb-2 text-[10px] font-mono tracking-wider uppercase text-slate-500">
              System Modules
            </div>
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? 'bg-gradient-to-r from-cyan-500/20 to-teal-500/10 text-cyan-300 border-l-4 border-cyan-400 shadow-glow-cyan/20'
                        : 'text-slate-400 hover:text-slate-100 hover:bg-cyan-500/5'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Footer Info in Sidebar */}
        <div className="p-4 border-t border-cyan-500/15 text-[11px] text-slate-500 space-y-1 bg-navy-950/40">
          <div className="flex items-center justify-between">
            <span>Sampling Clock:</span>
            <span className="font-mono text-slate-400">1000 Hz</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Sensor Spacing:</span>
            <span className="font-mono text-slate-400">2.0 Meters</span>
          </div>
        </div>
      </aside>
    </>
  );
};
