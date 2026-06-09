import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AgentsPage from "./pages/AgentsPage";
import DashboardPage from "./pages/DashboardPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import ProvidersPage from "./pages/ProvidersPage";
import StatusPage from "./pages/StatusPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/playground" element={<PlaygroundPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/status" element={<StatusPage />} />
      </Routes>
    </Layout>
  );
}
