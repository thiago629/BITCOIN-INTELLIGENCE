import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { ApiError } from "./api/client";
import { Layout } from "./components/Layout";
import { PageHeader } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { AddressPage, BlockPage, ExplorerHome, TxPage } from "./pages/Explorer";
import { SystemPage } from "./pages/System";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: false,
        // Do not retry "not found" / validation errors; retry transient ones once.
        retry: (count, err) => !(err instanceof ApiError && [404, 422, 429].includes(err.status)) && count < 1,
      },
    },
  });
}

function NotFound() {
  return (
    <PageHeader title="Página no encontrada">
      <Link className="link" to="/">Volver al Dashboard</Link>
    </PageHeader>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="explorer" element={<ExplorerHome />} />
        <Route path="block/:hash" element={<BlockPage />} />
        <Route path="tx/:txid" element={<TxPage />} />
        <Route path="address/:address" element={<AddressPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={makeQueryClient()}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
