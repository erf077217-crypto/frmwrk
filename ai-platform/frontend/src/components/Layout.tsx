import { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded text-sm font-medium ${
    isActive ? "bg-indigo-700 text-white" : "text-indigo-200 hover:bg-indigo-600"
  }`;

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-indigo-800 shadow">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center h-14 space-x-4">
            <span className="text-white font-bold text-lg mr-6">AI Platform</span>
            <NavLink to="/" className={linkClass} end>
              Dashboard
            </NavLink>
            <NavLink to="/providers" className={linkClass}>
              Providers
            </NavLink>
            <NavLink to="/playground" className={linkClass}>
              Playground
            </NavLink>
            <NavLink to="/agents" className={linkClass}>
              Agents
            </NavLink>
            <NavLink to="/status" className={linkClass}>
              System Status
            </NavLink>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
