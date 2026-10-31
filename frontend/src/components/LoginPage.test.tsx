import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { LoginPage } from "./LoginPage";

async function fillAndSubmit(button: RegExp) {
  await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: button }));
}

describe("LoginPage", () => {
  it("logs in and hands the user to the app", async () => {
    const user = { id: 1, email: "alice@example.com" };
    const login = vi.spyOn(api, "login").mockResolvedValue(user);
    const onLoggedIn = vi.fn();
    render(<LoginPage onLoggedIn={onLoggedIn} />);

    await fillAndSubmit(/^Log in$/);

    expect(login).toHaveBeenCalledWith("alice@example.com", "correct horse battery");
    expect(onLoggedIn).toHaveBeenCalledWith(user);
  });

  it("shows the server's error message when login fails", async () => {
    vi.spyOn(api, "login").mockRejectedValue(
      new ApiError(401, "invalid_credentials", "Invalid email or password."),
    );
    render(<LoginPage onLoggedIn={() => {}} />);

    await fillAndSubmit(/^Log in$/);

    expect(screen.getByRole("alert").textContent).toBe("Invalid email or password.");
  });

  it("can switch to creating an account", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue({ id: 2, email: "alice@example.com" });
    render(<LoginPage onLoggedIn={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /Create an account/ }));
    expect(screen.getByText(/At least 12 characters/)).toBeTruthy();
    await fillAndSubmit(/^Create account$/);

    expect(register).toHaveBeenCalledWith("alice@example.com", "correct horse battery");
  });
});
