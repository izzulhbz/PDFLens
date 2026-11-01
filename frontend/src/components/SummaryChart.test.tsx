import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SummaryChart as Chart } from "../types";
import { niceTicks, SummaryChart } from "./SummaryChart";

const enrolment: Chart = {
  title: "Enrolment by year",
  kind: "bar",
  x_label: "Year",
  y_label: "Students",
  points: [
    { label: "2021", value: 1200 },
    { label: "2022", value: 1350 },
    { label: "2023", value: 1420.5 },
  ],
  pages: [4],
};

describe("niceTicks", () => {
  it("covers the data with round steps", () => {
    expect(niceTicks(0, 1420.5)).toEqual([0, 500, 1000, 1500]);
    expect(niceTicks(-3, 7)).toEqual([-5, -2.5, 0, 2.5, 5, 7.5]);
  });

  it("gives a flat series room above and below", () => {
    const ticks = niceTicks(5, 5);
    expect(ticks[0]).toBeLessThan(5);
    expect(ticks[ticks.length - 1]).toBeGreaterThan(5);
  });
});

describe("SummaryChart", () => {
  it("draws one bar per point, cites its page, and offers the data as a table", async () => {
    const { container } = render(<SummaryChart chart={enrolment} />);

    expect(screen.getByRole("img", { name: /Bar chart: Enrolment by year/ })).toBeTruthy();
    expect(container.querySelectorAll(".chart-bar")).toHaveLength(3);
    expect(screen.getByText("p. 4")).toBeTruthy();

    await userEvent.click(screen.getByText("Show data"));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows.map((r) => r.textContent)).toEqual(["YearStudents", "20211,200", "20221,350", "20231,420.5"]);
  });

  it("draws a line chart with a marker per point", () => {
    const { container } = render(<SummaryChart chart={{ ...enrolment, kind: "line" }} />);

    expect(container.querySelector(".chart-line")).toBeTruthy();
    expect(container.querySelectorAll(".chart-marker")).toHaveLength(3);
  });

  it("shows a tooltip with the value on hover", () => {
    const { container } = render(<SummaryChart chart={enrolment} />);

    fireEvent.mouseEnter(container.querySelectorAll(".chart-hit")[1]!);

    expect(container.querySelector(".chart-tooltip")?.textContent).toBe("2022: 1,350");
  });

  it("renders labels from the model as text, never as markup", () => {
    const hostile = { ...enrolment, title: "<img src=x onerror=alert(1)>" };
    const { container } = render(<SummaryChart chart={hostile} />);

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
  });
});
