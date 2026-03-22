import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});
