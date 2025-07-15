import upstox_client
from upstox_client.rest import ApiException

# API version
api_version = '2.0'

# Create an instance of the HistoryApi
api_instance = upstox_client.HistoryApi()

# Instrument key for which historical data is needed
instrument_key = 'NSE_EQ|INE155A01022'  # Example instrument key

# Interval for candle data - can be '1minute', '30minute', 'day', 'month', etc.
interval = 'day'

# Date range for historical data (YYYY-MM-DD)
from_date = '2025-05-25'
to_date = '2025-05-30'

try:
    # Call the API to get historical candle data
    api_response = api_instance.get_historical_candle_data1(instrument_key, interval, to_date, from_date, api_version)
    print(api_response)
except ApiException as e:
    print("Exception when calling HistoryApi->get_historical_candle_data: %s\n" % e)
