import { describe, expect, it } from "vitest";
import { ApiError, errorText, isAuthError, serverDetail } from "./client";

describe("foutregels in de UI", () => {
  it("noemt een verlopen sessie bij naam", () => {
    const err = new ApiError(401, "Ongeldige of ontbrekende bearer-token");
    expect(isAuthError(err)).toBe(true);
    expect(errorText(err)).toContain("niet ingelogd");
  });

  it("legt de brute-force-rem uit in plaats van de status te tonen", () => {
    expect(errorText(new ApiError(429, "te snel"))).toContain("wacht een minuut");
  });

  it("toont status en detail bij een serverfout", () => {
    expect(errorText(new ApiError(500, "boem"))).toBe("500 — boem");
  });

  it("scheidt offline van onbereikbaar", () => {
    expect(errorText(new ApiError(0, "offline"))).toBe("geen verbinding");
    expect(errorText(new ApiError(502, "intervals"))).toContain("502");
  });

  it("valt terug op onbekend bij iets dat geen ApiError is", () => {
    expect(errorText(new Error("stuk"))).toBe("onbekende fout");
  });
});

describe("serverDetail", () => {
  it("laat de server-uitleg staan in plaats van een generiek zinnetje", () => {
    const err = new ApiError(502, "De TrainingPeaks-cookie is verlopen.");
    expect(serverDetail(err, "probeer het later opnieuw.")).toBe(
      "De TrainingPeaks-cookie is verlopen.",
    );
  });

  it("zegt bij offline dat het aan de verbinding ligt, niet aan TP", () => {
    expect(serverDetail(new ApiError(0, "offline"), "fallback")).toContain(
      "geen verbinding",
    );
  });

  it("valt terug als er geen detail of geen ApiError is", () => {
    expect(serverDetail(new ApiError(500, ""), "fallback")).toBe("fallback");
    expect(serverDetail(new Error("stuk"), "fallback")).toBe("fallback");
  });
});
