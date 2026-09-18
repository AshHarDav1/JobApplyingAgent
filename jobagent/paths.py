from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ENV_PATH = ROOT / ".env"
CONFIG_PATH = ROOT / "config.yaml"
SESSION_PATH = DATA_DIR / "user"
DB_PATH = DATA_DIR / "jobs.db"
CSV_PATH = DATA_DIR / "applied.csv"
XLSX_PATH = DATA_DIR / "applied.xlsx"
