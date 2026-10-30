import { Link } from "react-router";

/**
 * Catch-all for the laptop website.
 *
 * Phone URLs from v1 (`/`, `/spasht`, …) land here too, which is intentional:
 * the customer journey moved to the native iOS app, and there is nothing on the
 * website to send a customer to.
 */
export function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-navy text-4xl font-bold">404</p>
      <p className="text-text-3 text-body">That page does not exist on this website.</p>
      <p className="text-text-3 max-w-md text-caption">
        The website is the lender and compliance dashboard. The customer journey runs in the Spasht
        iPhone app.
      </p>
      <Link to="/dashboard" className="text-link text-body font-semibold">
        Go to the dashboard
      </Link>
    </div>
  );
}
