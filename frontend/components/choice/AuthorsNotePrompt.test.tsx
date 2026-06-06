import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";

import { AuthorsNotePrompt } from "./AuthorsNotePrompt";

test("renders one visible note input with the guidance inside and the submit button below it", async () => {
  const onSubmit = vi.fn();

  function Harness() {
    const [value, setValue] = useState("");

    return (
      <AuthorsNotePrompt
        value={value}
        placeholder="如：节奏慢一点 / 多内心独白"
        ariaLabel="想说点偏好（可选）"
        ctaLabel="进入故事"
        onChange={setValue}
        onSubmit={onSubmit}
      />
    );
  }

  render(<Harness />);

  const input = screen.getByRole("textbox", { name: "想说点偏好（可选）" });
  const button = screen.getByRole("button", { name: "进入故事" });

  expect(input).toHaveAttribute("placeholder", "如：节奏慢一点 / 多内心独白");
  expect(input).toHaveClass("lv-authors-note-input");
  expect(input.tagName).toBe("INPUT");
  expect(button).toHaveClass("lv-authors-note-button");
  expect(input.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  await userEvent.type(input, "慢一点");
  expect(input).toHaveValue("慢一点");

  await userEvent.click(button);
  expect(onSubmit).toHaveBeenCalledTimes(1);
});
