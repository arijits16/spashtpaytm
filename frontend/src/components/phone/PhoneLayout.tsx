import { Outlet } from "react-router";
import { PhoneFrame } from "./PhoneFrame";

/** Route layout for every customer-facing phone route (build plan 5.8). */
export function PhoneLayout() {
  return (
    <PhoneFrame>
      <Outlet />
    </PhoneFrame>
  );
}
