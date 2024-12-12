from __future__ import absolute_import, unicode_literals
from celery import shared_task
import pandas as pd
import bnbu_constants.constants as constants
from bnbu_constants.utility import (
    calculate_monthly_profit,
    calculate_utilities,
    determine_property_status,
    process_airdna_api
)
from rental.models import RentalProperty
from datetime import datetime
import logging
from io import StringIO

logger = logging.getLogger(__name__)

@shared_task
def process_rental_properties_task(cleaned_df_json, batch_id):
    try:
        # Convert JSON back to DataFrame
        cleaned_df = pd.read_json(StringIO(cleaned_df_json))  # Wrap JSON in StringIO
        logger.info("Loaded DataFrame from JSON. Batch ID: %s, Rows: %d", batch_id, len(cleaned_df))
    except Exception as e:
        logger.error("Error loading DataFrame from JSON: %s", e, exc_info=True)
        raise

    batch_size = 25
    results = []

    for i in range(0, len(cleaned_df), batch_size):
        bulk_queries = []
        data_chunk = cleaned_df.iloc[i:i + batch_size]
        logger.info("Processing chunk %d to %d. Total rows: %d", i, i + len(data_chunk), len(data_chunk))

        for row in data_chunk.itertuples(index=False):
            query = {
                "address": row.Location,
                "bedrooms": row.Br,
                "bathrooms": row.Ba,
                "accommodates": row.Br * 2 if row.Br else None,
                "currency": constants.CURRENCY_USD,
            }
            bulk_queries.append(query)

        try:
            response = process_airdna_api(bulk_queries)
            logger.info("Received API response for %d properties", len(bulk_queries))
        except Exception as e:
            logger.error("Error calling AirDNA API: %s", e, exc_info=True)
            continue

        relevant_information = [
            {
                'ADR': entry['stats']['future']['summary'].get('adr'),
                'Occupancy': entry['stats']['future']['summary'].get('occupancy'),
                'Revenue': entry['stats']['future']['summary'].get('revenue'),
                'Location': entry['details']['address'],
            }
            for entry in response
        ]
        response_dataframe = pd.DataFrame(relevant_information)
        merged_df = pd.merge(data_chunk, response_dataframe, on='Location', how='left')
        logger.debug("Merged DataFrame for chunk %d to %d:\n%s", i, i + len(data_chunk), merged_df)

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
        logger.info("Calculated additional metrics for chunk %d to %d", i, i + len(data_chunk))

        # Save processed properties
        for _, row in merged_df.iterrows():
            try:
                rental_property = RentalProperty(
                    location=row['Location'],
                    rent=row['Price'],
                    no_of_bedrooms=row['Br'],
                    no_of_bathrooms=row['Ba'],
                    square_feet=row['Sq. ft.'],
                    property_zillow_link=row['Link'],
                    adr=row['ADR'], 
                    occupancy_rate=row['Occupancy'],
                    utilities=row['utilities'],
                    yearly_projected_revenue=row['Revenue'],
                    monthly_estimated_profit=row['monthly_estimated_profit'],
                    batch_id=batch_id,
                    property_status=row['property_status'],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                rental_property.yearly_rent_cost_util = calculate_monthly_profit(
                    rental_property.yearly_projected_revenue, rental_property.rent, rental_property.no_of_bedrooms
                )[2]
                rental_property.save()
                logger.debug("Saved RentalProperty: %s", rental_property)
            except Exception as e:
                logger.error("Error saving RentalProperty for Location: %s. Error: %s", row['Location'], e, exc_info=True)

        results.append(merged_df)

    try:
        result_json = pd.concat(results).to_json(orient='records')
        logger.info("Successfully processed all chunks for Batch ID: %s", batch_id)
        return result_json
    except Exception as e:
        logger.error("Error concatenating results: %s", e, exc_info=True)
        raise
