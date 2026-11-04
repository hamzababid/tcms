import { ApiError, readCookie, toApiError } from "./client";

describe("api client", () => {
  it("parses problem+json into ApiError", async () => {
    const response = new Response(
      JSON.stringify({
        type: "x",
        title: "Validation failed",
        status: 422,
        code: "validation_error",
        detail: null,
        request_id: "req_1",
        errors: [{ field: "name", code: "too_short", message: "Too short" }],
      }),
      { status: 422, headers: { "content-type": "application/problem+json" } },
    );
    const error = await toApiError(response);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("validation_error");
    expect(error.detail).toBe("Validation failed");
    expect(error.errors[0]?.field).toBe("name");
    expect(error.requestId).toBe("req_1");
  });

  it("tolerates non-JSON error bodies", async () => {
    const error = await toApiError(
      new Response("bad gateway", { status: 502, headers: { "x-request-id": "req_2" } }),
    );
    expect(error.code).toBe("http_error");
    expect(error.requestId).toBe("req_2");
  });

  it("reads the CSRF cookie", () => {
    expect(readCookie("tcms_csrf", "a=1; tcms_csrf=abc%3D; b=2")).toBe("abc=");
    expect(readCookie("missing", "a=1")).toBeNull();
  });
});
