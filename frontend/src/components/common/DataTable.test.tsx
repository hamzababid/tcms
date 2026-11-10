import { fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DataTable, usePaging } from "./DataTable";

interface Row {
  id: string;
  name: string;
  role: string;
}

const rows: Row[] = Array.from({ length: 30 }, (_, i) => ({
  id: String(i + 1),
  name: `Person ${String(i + 1).padStart(2, "0")}`,
  role: i % 3 === 0 ? "lead" : "engineer",
}));

const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name", meta: { filter: { kind: "text" } } },
  {
    accessorKey: "role",
    header: "Role",
    meta: {
      filter: {
        kind: "select",
        options: [
          { value: "lead", label: "Lead" },
          { value: "engineer", label: "Engineer" },
        ],
      },
    },
  },
];

const table = () =>
  render(
    <DataTable
      label="People"
      columns={columns}
      data={rows}
      getRowId={(r) => r.id}
      noun={["person", "people"]}
    />,
  );
const bodyRows = () =>
  within(screen.getByRole("table", { name: "People" }))
    .getAllByRole("row")
    .slice(2);

describe("DataTable", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("pages with a default size of 50 and a page size selector", () => {
    table();
    expect(screen.getByText("Showing 1–30 of 30")).toBeTruthy();
    expect(bodyRows()).toHaveLength(30);
    fireEvent.change(screen.getByRole("combobox", { name: "Rows per page" }), { target: { value: "25" } });
    expect(bodyRows()).toHaveLength(25);
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Showing 26–30 of 30")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Rows per page" }), { target: { value: "10" } });
    expect(screen.getByText("Showing 1–10 of 30")).toBeTruthy();
    expect(screen.getByText("Page 1 of 3")).toBeTruthy();
  });

  it("filters per column (select immediately, text after a short pause) and clears", () => {
    table();
    fireEvent.change(screen.getByRole("combobox", { name: "Filter Role" }), { target: { value: "lead" } });
    expect(screen.getByText("10 people")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "Filter Name" }), {
      target: { value: "Person 01" },
    });
    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(screen.getByText("1 person")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Clear filters/ }));
    expect(screen.getByText("30 people")).toBeTruthy();
    expect(screen.getByRole<HTMLInputElement>("searchbox", { name: "Filter Name" }).value).toBe("");
  });

  it("sorts by a column header", () => {
    table();
    fireEvent.click(screen.getByRole("button", { name: /Name/ }));
    fireEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(within(bodyRows()[0] as HTMLElement).getByText("Person 30")).toBeTruthy();
  });

  it("server mode without a sort or filter API shows no sort buttons and no filter row", () => {
    render(
      <DataTable
        label="People"
        columns={columns}
        data={rows.slice(0, 5)}
        server={{ total: 5, pagination: { pageIndex: 0, pageSize: 50 }, onPaginationChange: () => undefined }}
      />,
    );
    expect(screen.queryByRole("button", { name: /^Name/ })).toBeNull();
    expect(screen.queryByRole("searchbox", { name: "Filter Name" })).toBeNull();
    expect(screen.getByText("Showing 1–5 of 5")).toBeTruthy();
  });

  it("server mode: a page past the end moves to the last page", () => {
    const onPage = vi.fn();
    render(
      <DataTable
        label="People"
        columns={columns}
        data={[]}
        server={{ total: 30, pagination: { pageIndex: 4, pageSize: 10 }, onPaginationChange: onPage }}
      />,
    );
    expect(onPage).toHaveBeenCalledWith({ pageIndex: 2, pageSize: 10 });
  });
});

describe("usePaging", () => {
  it("goes back to page 1 when the key changes and keeps the page size", () => {
    const { result, rerender } = renderHook(({ k }) => usePaging(k), { initialProps: { k: "a" } });
    act(() => {
      result.current[1]({ pageIndex: 3, pageSize: 25 });
    });
    expect(result.current[0]).toEqual({ pageIndex: 3, pageSize: 25 });
    rerender({ k: "b" });
    expect(result.current[0]).toEqual({ pageIndex: 0, pageSize: 25 });
  });
});
