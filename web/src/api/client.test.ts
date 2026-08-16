import { describe, expect, it } from "vitest";
import { ApiError, errorText, isAuthError } from "./client";

describe("foutregels in de UI", () => {
  it("noemt een verlopen koppeling bij naam", () => {
    const err = new ApiError(401, "Ongeldige of ontbrekende bearer-token");
    expect(isAuthError(err)).toBe(true);
    expect(errorText(err)).toContain("niet gekoppeld");
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
