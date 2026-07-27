"""ZMP — Entry point. Launches native CustomTkinter window."""
from __future__ import annotations


def main() -> None:
    from .app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
