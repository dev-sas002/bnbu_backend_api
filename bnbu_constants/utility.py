import bnbu_constants.constants as constants
import pandas as pd 
from bnbu_backend_api.settings import AIRDNA_URL, AIRDNA_API_KEY
import requests

def validate_file_type(file):
    if not file.endswith(tuple(constants.VALID_FILE_EXTENSION)):
        return False
    return True


def file_to_df(file):
    if file.endswith(".csv"):
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
    return df

def clean_price(price):
    try:
        return int(str(price).replace("$", "").replace("/mo", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def process_airdna_api(bulk_queries):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AIRDNA_API_KEY}",
    }
    payload = {"queries": bulk_queries}

    retry_count = 5
    retries = 0

    while retry_count > retries:
        try:
            response = requests.post(AIRDNA_URL, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["payload"]["results"]
        except Exception as e:
            retries += 1
    raise ValueError("AirDNA API Request Fails !!!")

def calculate_utilities(no_of_bedroom):
    return no_of_bedroom * 2000

def process_rental_properties(cleaned_df):

    batch_size = 25

    for i in range(0, len(cleaned_df), batch_size):
        bulk_queries = []
        data_chunk = cleaned_df.iloc[i:i + batch_size]
        for row in data_chunk.itertuples(index=False):
            query = {
                "address": row.Location,
                "bedrooms": row.Br,
                "bathrooms": row.Ba,
                "accommodates": row.Br * 2 if row.Br else None,
                "currency": constants.CURRENCY_USD,
            }
            bulk_queries.append(query)

        response =  process_airdna_api(bulk_queries)
        revelant_information = [
                            {
                                'ADR': entry['stats']['future']['summary'].get('adr'),
                                'Occupancy': entry['stats']['future']['summary'].get('occupancy'),
                                'Revenue': entry['stats']['future']['summary'].get('revenue'),
                                'Location': entry['details']['address'],
                            }
                            for entry in response
                        ]
        response_dataframe = pd.DataFrame(revelant_information)
        merged_df = pd.merge(cleaned_df, response_dataframe, on='Location', how='left')
        merged_df['utilities'] = merged_df['Br'].apply(calculate_utilities)
    return merged_df


