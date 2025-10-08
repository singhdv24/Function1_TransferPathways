#!/usr/bin/env python3
# individual_transfer_app.py
# A minimal app to analyze ONE AS plan vs ONE BS plan using a course equivalency Excel.
# Run:  uvicorn not required — just `python individual_transfer_app.py`

import os
import tempfile
import pandas as pd
import gradio as gr

# -------------------------
# Helpers
# -------------------------
AS_DEFAULT_CODE_COLS = ["Course_Name", "Course Code", "Course_Code", "Code"]
AS_DEFAULT_CREDITS_COLS = ["Credit_Hours", "Credits", "Credit Hours"]
BS_DEFAULT_CODE_COLS = ["Name", "Course_Name", "Course Code", "Code", "Course_Code"]
EQUIV_AS_CODE_COLS = ["Course_Code", "AS_Code"]
EQUIV_BS_CODE_COL = "Equivalent Course Code"

def _first_existing_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(f"None of the expected columns found. Looked for: {candidates} in columns: {list(df.columns)}")

def normalize_code(code):
    if pd.isna(code):
        return None
    return str(code).replace('\xa0', ' ').replace(' ', ' ').strip().upper()

def parse_as_df(df: pd.DataFrame):
    code_col = _first_existing_col(df, AS_DEFAULT_CODE_COLS)
    credits_col = _first_existing_col(df, AS_DEFAULT_CREDITS_COLS)
    out = pd.DataFrame({
        "Normalized_Code": df[code_col].apply(normalize_code),
        "Credit_Hours": pd.to_numeric(df[credits_col], errors="coerce")
    })
    out = out.dropna(subset=["Normalized_Code", "Credit_Hours"])
    return out

def parse_bs_df(df: pd.DataFrame):
    code_col = _first_existing_col(df, BS_DEFAULT_CODE_COLS)
    out = pd.DataFrame({
        "Normalized_Code": df[code_col].apply(normalize_code),
    })
    out = out.dropna(subset=["Normalized_Code"])
    return out

def parse_equiv_df(df: pd.DataFrame, sheet_name=None):
    # If a specific sheet name isn't given, just use the first sheet; caller passes the already-parsed frame.
    as_col = None
    for c in EQUIV_AS_CODE_COLS:
        if c in df.columns:
            as_col = c
            break
    if as_col is None:
        raise ValueError(f"Could not find any AS code column among: {EQUIV_AS_CODE_COLS}")
    if EQUIV_BS_CODE_COL not in df.columns:
        raise ValueError(f"Could not find BS code column '{EQUIV_BS_CODE_COL}' in equivalency file.")

    equiv = pd.DataFrame({
        "AS_Code": df[as_col].apply(normalize_code),
        "BS_Codes": df[EQUIV_BS_CODE_COL].astype(str).str.split(";").apply(lambda xs: [normalize_code(x) for x in xs if x])
    })
    # Drop rows missing AS codes
    equiv = equiv.dropna(subset=["AS_Code"])
    return equiv

def compute_transfer(as_df: pd.DataFrame, bs_df: pd.DataFrame, equiv_df: pd.DataFrame):
    # Build BS code set
    bs_codes = set(bs_df["Normalized_Code"].dropna().tolist())

    # Build equivalency lookup: AS -> set(BS)
    equiv_map = {}
    for _, row in equiv_df.iterrows():
        as_code = row["AS_Code"]
        if pd.isna(as_code) or not as_code:
            continue
        bs_list = row["BS_Codes"] if isinstance(row["BS_Codes"], list) else []
        bs_clean = {c for c in bs_list if c}
        if as_code not in equiv_map:
            equiv_map[as_code] = set()
        equiv_map[as_code].update(bs_clean)

    total = float(as_df["Credit_Hours"].sum() or 0.0)
    matched = 0.0
    unmatched_rows = []

    for _, row in as_df.iterrows():
        code = row["Normalized_Code"]
        cr = float(row["Credit_Hours"] or 0.0)
        bs_equivs = equiv_map.get(code, set())
        # Count as matched if ANY BS equivalent appears in the BS plan
        ok = any(b in bs_codes for b in bs_equivs)
        if ok:
            matched += cr
        else:
            unmatched_rows.append({"AS Course Code": code, "Credits": cr})

    lost = max(0.0, total - matched)
    loss_score = round(lost / total, 4) if total > 0 else 1.0

    summary = pd.DataFrame([{
        "Total AS Credits": total,
        "Matched Credits": matched,
        "Lost Credits": lost,
        "Loss Score (0=perfect)": loss_score
    }])

    unmatched = pd.DataFrame(unmatched_rows)
    return summary, unmatched

# -------------------------
# Core function for Gradio
# -------------------------
def run_individual(as_file, bs_file, equiv_file, equiv_sheet_name):
    """
    Inputs:
      - as_file: .xlsx for ONE AS plan
      - bs_file: .xlsx for ONE BS plan
      - equiv_file: course equivalency .xlsx
      - equiv_sheet_name: optional sheet name (blank = first sheet)
    """
    if as_file is None or bs_file is None or equiv_file is None:
        return "Please upload all three files.", None, None, None

    # Load dataframes
    as_df_raw = pd.read_excel(as_file.name)
    bs_df_raw = pd.read_excel(bs_file.name)
    if equiv_sheet_name and str(equiv_sheet_name).strip():
        equiv_df_raw = pd.read_excel(equiv_file.name, sheet_name=str(equiv_sheet_name).strip())
    else:
        equiv_df_raw = pd.read_excel(equiv_file.name, sheet_name=0)

    # Parse
    try:
        as_df = parse_as_df(as_df_raw)
    except Exception as e:
        return f"AS file parsing error: {e}", None, None, None
    try:
        bs_df = parse_bs_df(bs_df_raw)
    except Exception as e:
        return f"BS file parsing error: {e}", None, None, None
    try:
        equiv_df = parse_equiv_df(equiv_df_raw)
    except Exception as e:
        return f"Equivalency file parsing error: {e}", None, None, None

    # Compute
    summary_df, unmatched_df = compute_transfer(as_df, bs_df, equiv_df)

    # Save CSVs for download
    tmpdir = tempfile.gettempdir()
    summary_path = os.path.join(tmpdir, "individual_summary.csv")
    unmatched_path = os.path.join(tmpdir, "individual_unmatched_courses.csv")
    as_norm_path = os.path.join(tmpdir, "individual_as_normalized.csv")
    bs_norm_path = os.path.join(tmpdir, "individual_bs_normalized.csv")

    summary_df.to_csv(summary_path, index=False)
    unmatched_df.to_csv(unmatched_path, index=False)
    as_df.to_csv(as_norm_path, index=False)
    bs_df.to_csv(bs_norm_path, index=False)

    return (
        "✅ Analysis complete.",
        summary_df,
        unmatched_df,
        [summary_path, unmatched_path, as_norm_path, bs_norm_path]
    )

# -------------------------
# Gradio UI
# -------------------------
with gr.Blocks(title="Individual AS→BS Transfer Analyzer") as demo:
    gr.Markdown("## Individual AS→BS Transfer Analyzer\nUpload **one** AS plan, **one** BS plan, and the **course equivalencies** Excel. Optionally specify a sheet name (leave blank for the first sheet).")
    with gr.Row():
        as_file = gr.File(label="Upload ONE AS Plan (.xlsx)")
        bs_file = gr.File(label="Upload ONE BS Plan (.xlsx)")
    with gr.Row():
        equiv_file = gr.File(label="Upload Course Equivalencies (.xlsx)")
        equiv_sheet = gr.Textbox(label="Equivalency Sheet Name (optional)", placeholder="e.g., Community College")
    run_btn = gr.Button("Run Analysis")
    status = gr.Markdown()
    summary_out = gr.Dataframe(label="Summary")
    unmatched_out = gr.Dataframe(label="Unmatched AS Courses")
    downloads = gr.Files(label="Download CSVs (summary, unmatched, normalized inputs)")

    run_btn.click(
        fn=run_individual,
        inputs=[as_file, bs_file, equiv_file, equiv_sheet],
        outputs=[status, summary_out, unmatched_out, downloads]
    )

if __name__ == "__main__":
    demo.launch()
