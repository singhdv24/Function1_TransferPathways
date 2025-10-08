cat > README.md << 'EOF'
# Function 1 – Transfer Pathways Toolkit

Undergraduate research under **Dr. David Reeping** (University of Cincinnati).

## Tools
- **lost_credit_calculator/** — compute AS→BS credit transfer, show total/matched/lost, export CSV.
- **combine_plans_of_study/** — merge one AS plan + one BS plan into a formatted combined plan (XLSX).

## Quickstart
```bash
python -m venv .venv
.\.venv\Scripts\activate    # Windows
pip install -r requirements.txt

# run lost credit UI
python lost_credit_calculator/individual_transfer_app.py

# run combined plan UI
python combine_plans_of_study/combine_plans_app.py
