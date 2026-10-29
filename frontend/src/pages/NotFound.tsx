import { Link } from "react-router";

export function NotFound() {
  return (
    <div className="px-screen flex min-h-full flex-col items-center justify-center gap-3 text-center">
      <p className="text-navy text-4xl font-bold">404</p>
      <p className="text-text-3 text-body">That screen does not exist in this prototype.</p>
      <Link to="/" className="text-link text-body font-semibold">
        Back to home
      </Link>
    </div>
  );
}
