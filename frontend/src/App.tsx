import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { router } from "@/routes";

/**
 * Query defaults tuned for a live demo on venue Wi-Fi: no refetch storms when
 * the window regains focus, one quick retry, and data treated as fresh for a
 * few seconds so re-renders do not re-hit the backend.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
