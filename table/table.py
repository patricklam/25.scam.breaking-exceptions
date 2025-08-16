#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import pandas as pd
import math

def latex_escape(s: str) -> str:
    if pd.isna(s):
        return ""
    s = str(s)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s

def pick_column(df, candidates):
    cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        k = cand.lower().strip()
        if k in cols:
            return cols[k]
    for cand in candidates:
        k = cand.lower().strip()
        for lc, orig in cols.items():
            if k == lc or k in lc:
                return orig
    return None

def build_latex_table(df: pd.DataFrame, caption: str, label: str, table_star: bool):
    begin_env = "table*" if table_star else "table"
    colspec = r""">{\raggedright\arraybackslash\hangindent=2em}p{3.5cm} >{\raggedright\arraybackslash\hangindent=2em}p{3.5cm} >{\raggedright\arraybackslash\hangindent=2em}p{3.5cm} >{\raggedleft\arraybackslash}p{2cm} >{\raggedleft\arraybackslash}p{2cm}"""
    lines = []
    lines.append(fr"\begin{{{begin_env}}}[hbt!]")
    lines.append(r"\centering")
    lines.append(fr"\caption{{{caption}}}")
    lines.append(fr"\label{{{label}}}")
    lines.append(fr"\begin{{tabular}}{{{colspec}}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Client} & \textbf{Current Version} & \textbf{Latest Version} & \textbf{Number of Callsites} & \textbf{Reachable Callsites} \\")
    lines.append(r"\midrule")

    # We're sorted in caller; just add spacing when (LibraryOld, LibraryNew) changes
    last_pair = (None, None)
    for i, row in df.iterrows():
        pair = (row.get("LibraryOld", ""), row.get("LibraryNew", ""))
        if i > 0 and pair != last_pair:
            lines.append(r"\addlinespace")
        last_pair = pair

        client = latex_escape(row.get("ClientName", ""))
        oldv = latex_escape(row.get("LibraryOld", ""))
        newv = latex_escape(row.get("LibraryNew", ""))

        def fmt_int(x):
            if pd.isna(x) or x == "":
                return ""
            try:
                f = float(x)
                if math.isnan(f):
                    return ""
                return str(int(f))
            except Exception:
                try:
                    return str(int(str(x).strip()))
                except Exception:
                    return latex_escape(str(x))

        num_calls = fmt_int(row.get("NumCallsites", ""))
        reachable = fmt_int(row.get("Reachable", ""))

        lines.append(f"{client} & {oldv} & {newv} & {num_calls} & {reachable} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(fr"\end{{{begin_env}}}")
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser(description="Create a LaTeX table from a CSV.")
    p.add_argument("csv_path", help="Path to input CSV")
    p.add_argument("-o", "--output", default="table.tex", help="Output .tex file path")
    p.add_argument("--caption", default="Clients, libraries, versions, and counts of callsites reaching newly-added exceptions")
    p.add_argument("--label", default="tab:version-changes")
    p.add_argument("--no-table-star", action="store_true", help="Use \\begin{table} instead of \\begin{table*}")
    p.add_argument("--top", type=int, default=15, help="Keep only the top N rows by Reachable Callsites (desc)")
    args = p.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: CSV not found at {csv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        df = pd.read_csv(csv_path, engine="python")
    except Exception:
        df = pd.read_csv(csv_path)

    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    client_col = pick_column(df, ["ClientName", "Client", "Client Name"])
    old_col    = pick_column(df, ["LibraryOld", "OldVersion", "Current Version", "Library Old"])
    new_col    = pick_column(df, ["LibraryNew", "NewVersion", "Latest Version", "Library New"])
    calls_col  = pick_column(df, ["Number of Times the Library is Used in the Client", "Number of Callsites", "NumCallsites"])
    reach_col  = pick_column(df, ["NumberOfMatchedMethods", "Reachable Callsites", "Reachable"])

    missing = [("ClientName", client_col), ("LibraryOld", old_col), ("LibraryNew", new_col), ("NumCallsites", calls_col), ("Reachable", reach_col)]
    missing_pretty = [name for name, col in missing if col is None]
    if missing_pretty:
        print("Warning: Could not find the following required columns in the CSV:", ", ".join(missing_pretty), file=sys.stderr)

    out = pd.DataFrame({
        "ClientName": df[client_col] if client_col else "",
        "LibraryOld": df[old_col] if old_col else "",
        "LibraryNew": df[new_col] if new_col else "",
        "NumCallsites": df[calls_col] if calls_col else "",
        "Reachable": df[reach_col] if reach_col else "",
    })

    # Numeric conversion and sorting
    out["Reachable"] = pd.to_numeric(out["Reachable"], errors="coerce").fillna(0)
    out["NumCallsites"] = pd.to_numeric(out["NumCallsites"], errors="coerce").fillna(0)

    # Primary sort: Reachable desc; tie-breakers: NumCallsites desc, then LibraryOld/New, then Client
    out_sorted = out.sort_values(
        ["Reachable", "NumCallsites", "LibraryOld", "LibraryNew", "ClientName"],
        ascending=[False, False, True, True, True]
    ).reset_index(drop=True)

    # Keep top N
    if args.top and args.top > 0:
        out_sorted = out_sorted.head(args.top)

    latex = build_latex_table(out_sorted, caption=args.caption, label=args.label, table_star=not args.no_table_star)
    Path(args.output).write_text(latex, encoding="utf-8")
    print(f"Wrote LaTeX table to {args.output}")

if __name__ == "__main__":
    main()
