# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/bnbu_constants/utility.py
import bnbu_constants.constants as constants
import pandas as pd 
from bnbu_backend_api.settings import AIRDNA_URL, AIRDNA_API_KEY
import requests

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

    print("=====> ", bulk_queries)
    while retry_count > retries:
        try:
            response = requests.post(AIRDNA_URL, json=payload, headers=headers)
            response.raise_for_status()
            # return response.json()["payload"]["results"]
            results = response.json()["payload"]["results"]
            # results = response.json().get("payload", {}).get("results", [])
            if not results:
                raise ValueError("No results returned from API.")
            return results
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            retries += 1

    raise ValueError("AirDNA API Request Fails !!!")

def calculate_utilities(no_of_bedroom):
    return no_of_bedroom * 2000

def calculate_monthly_profit(annual_revenue, monthly_rent, no_of_bedroom):
    if not annual_revenue or not monthly_rent or not no_of_bedroom:
        return None, None, None

    utilities = calculate_utilities(no_of_bedroom)
    yearly_rent_cost_util = (monthly_rent * 12) + utilities
    monthly_estimated_profit = (annual_revenue - yearly_rent_cost_util) / 12
    return utilities, annual_revenue, yearly_rent_cost_util, round(monthly_estimated_profit, 2)


def determine_property_status(no_of_bedrooms, monthly_estimated_profit):
    """Determine the property status based on number of bedrooms and monthly profit."""
    if monthly_estimated_profit is None:
        return "error"

    if no_of_bedrooms == 1 and monthly_estimated_profit >= 1000:
        return "approved"
    elif no_of_bedrooms == 2 and monthly_estimated_profit >= 1500:
        return "approved"
    elif no_of_bedrooms >= 3 and monthly_estimated_profit >= 2000:
        return "approved"
    else:
        return "rejected"


def process_rental_properties(cleaned_df, batch_id):

    batch_size = 25
    print(f"Processing DataFrame with {len(cleaned_df)} rows")

    for i in range(0, len(cleaned_df), batch_size):
        bulk_queries = []
        data_chunk = cleaned_df.iloc[i:i + batch_size]
        print(f"Processing batch {i} to {i + batch_size}")
        for row in data_chunk.itertuples(index=False):
            query = {
                "address": row.Location,
                "bedrooms": row.Br,
                "bathrooms": row.Ba,
                "accommodates": row.Br * 2 if row.Br else None,
                "currency": constants.CURRENCY_USD,
            }
            bulk_queries.append(query)
        print("Sending payload to AirDNA API:", bulk_queries)
        response =  process_airdna_api(bulk_queries)
        print("AirDNA API Response:", response)
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
        # Calculate utilities, monthly profit, and property status
        merged_df['utilities'] = merged_df['Br'].apply(calculate_utilities)
        merged_df['monthly_estimated_profit'] = merged_df.apply(
            lambda row: calculate_monthly_profit(row.Revenue, row.Price, row.Br)[-1],
            axis=1
        )

        merged_df['property_status'] = merged_df.apply(
            lambda row: determine_property_status(row.Br, row.monthly_estimated_profit),
            axis=1
        )

    return merged_df

