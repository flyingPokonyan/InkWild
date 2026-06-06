"use client";

interface JumpToLatestButtonProps {
  visible: boolean;
  onClick: () => void;
}

export function JumpToLatestButton({ visible, onClick }: JumpToLatestButtonProps) {
  if (!visible) return null;

  return (
    <button type="button" onClick={onClick} className="play-jump-latest">
      <span>回到最新</span>
      <span aria-hidden="true">↓</span>
    </button>
  );
}
