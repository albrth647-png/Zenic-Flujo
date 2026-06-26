// Setup global para vitest.
// Carga las custom matchers de @testing-library/jest-dom (toBeInTheDocument, etc.).
import "@testing-library/jest-dom/vitest"

// Silenciar console.error/ruido en tests (opcional, descomentar si hace falta)
// import { vi } from "vitest"
// vi.spyOn(console, "error").mockImplementation(() => {})
