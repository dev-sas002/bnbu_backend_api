import bnbu_constants.constants as constants
import pandas as pd 


def validate_file_type(file):
    if not file.name.endswith(tuple(constants.VALID_FILE_EXTENSION)):
        return False
    return True


def file_to_df(file):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    return df


def validate_df(df):
    missing_cols = []
    if any(col not in df.columns for col in constants.REQUIRED_COLS):
        missing_cols = set(constants.REQUIRED_COLS) - set(df.columns)
    return missing_cols

def normalize_column(df, col_name):
    df[col_name] = df[col_name].astype(str).str.extract('(\d+)').astype(float)

def normalize_df(df):
    df = df.dropna(subset=constants.IMP_COLS)

def extract_rent(price):
    try:
        return int(str(price).replace("$", "").replace("/mo", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None
