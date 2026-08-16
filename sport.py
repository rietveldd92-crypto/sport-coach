#!/usr/bin/env python
"""
sport — Eén entrypoint voor alle Sport Coach commando's.

Gebruik:
    python sport.py status                    # Huidige status (CTL, fase, injury)
    python sport.py plan                      # Plan komende week (dry run)
    python sport.py plan --schrijf            # Plan en schrijf naar intervals.icu
    python sport.py eval                      # Evalueer afgelopen week + plan volgende
    python sport.py eval --dry-run            # Alleen rapport
    python sport.py feedback "kniepijn"       # Geef feedback, pas week aan
    python sport.py feedback "alles goed"     # Positieve feedback
    python sport.py coach                     # Interactieve coach (feedback + swap)
    python sport.py coach --check             # Non-interactive feedback op voltooide workouts
    python sport.py week                      # Toon deze week
"""

import sys
from pathlib import Path

# Zorg dat imports werken
sys.path.insert(0, str(Path(__file__).parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

USAGE = """
  Sport Coach — Amsterdam Marathon 2026

  Commando's:
    status                         Huidige status (CTL, fase, injury guard)
    plan [--schrijf] [--week D]    Plan komende week (dry run tenzij --schrijf)
    eval [--dry-run] [--feedback]  Evalueer afgelopen week + plan volgende
    feedback "tekst"               Geef feedback, pas huidige week aan
    coach [--check]                Interactieve coach met feedback en swap
    week [--week YYYY-MM-DD]       Toon weekoverzicht
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        return

    cmd = sys.argv[1]
    # Verwijder het subcommando zodat argparse in de scripts werkt
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if cmd == "status":
        from plan_week import print_status
        print_status()

    elif cmd == "plan":
        from plan_week import main as plan_main
        plan_main()

    elif cmd == "eval":
        from evaluate_week import main as eval_main
        eval_main()

    elif cmd == "feedback":
        # Eerste arg na 'feedback' is de tekst
        if not sys.argv[1:]:
            sys.argv.append("--status")
        from adjust import main as adjust_main
        adjust_main()

    elif cmd == "coach":
        from coach import main as coach_main
        coach_main()

    elif cmd == "week":
        from coach import main as coach_main
        if "--check" not in sys.argv:
            sys.argv.append("--check")
        coach_main()

    else:
        print(f"  Onbekend commando: {cmd}")
        print(USAGE)


if __name__ == "__main__":
    main()
