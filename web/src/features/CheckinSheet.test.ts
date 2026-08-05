import { describe, expect, it } from "vitest";
import { parseOptionalWeight } from "./CheckinSheet";

describe("gewicht in de check-in", () => {
  it("laat het veld optioneel", () => {
    expect(parseOptionalWeight(" ")).toBeUndefined();
  });

  it("verwerkt een Nederlandse decimale komma", () => {
    expect(parseOptionalWeight("87,5")).toBe(87.5);
  });
});
