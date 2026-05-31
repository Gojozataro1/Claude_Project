# ============================================================
# WEEK 2 PROJECT: Fetch a ServiceNow Incident via REST API
# ============================================================
# WHAT THIS SCRIPT DOES:
#   1. Reads ServiceNow credentials from environment variables
#   2. Exchanges credentials for an OAuth token (more secure than Basic Auth)
#   3. Asks you for an incident number (e.g. INC0010034)
#   4. Calls the ServiceNow REST API to fetch that incident
#   5. Displays the incident details in a readable format
#
# HOW TO RUN:
#   python3 week2_servicenow_fetcher.py
# ============================================================


# --- STEP 1: Import libraries ---
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


# --- STEP 2: Read credentials from environment variables ---
# Never hardcode secrets in the script

SNOW_INSTANCE     = os.environ.get("SNOW_INSTANCE")
SNOW_USER         = os.environ.get("SNOW_USER")
SNOW_PASS         = os.environ.get("SNOW_PASS")
SNOW_CLIENT_ID     = os.environ.get("SNOW_CLIENT_ID")
SNOW_CLIENT_SECRET = os.environ.get("SNOW_CLIENT_SECRET")

if not all([SNOW_INSTANCE, SNOW_USER, SNOW_PASS, SNOW_CLIENT_ID, SNOW_CLIENT_SECRET]):
    print("ERROR: Missing credentials. Check your .env file.")
    exit(1)


# --- STEP 3: Get an OAuth token ---
# Instead of sending username+password with every request (Basic Auth),
# we exchange them ONCE for a short-lived token, then use the token.
#
# This is the OAuth 2.0 "Resource Owner Password" flow:
#   Script → sends credentials to /oauth_token.do → ServiceNow returns a token
#   Script → uses token for all API calls → token expires after a while

print("\nGetting OAuth token from ServiceNow...")

token_url = f"{SNOW_INSTANCE}/oauth_token.do"

# We send credentials as form data (not JSON) — this is what ServiceNow expects
token_data = {
    "grant_type":    "password",       # tells ServiceNow which OAuth flow we're using
    "client_id":     SNOW_CLIENT_ID,
    "client_secret": SNOW_CLIENT_SECRET,
    "username":      SNOW_USER,
    "password":      SNOW_PASS
}

try:
    token_response = requests.post(token_url, data=token_data)
    token_response.raise_for_status()

    # The response contains the token inside an "access_token" key
    access_token = token_response.json().get("access_token")

    if not access_token:
        print("ERROR: No access token received. Check your Client ID and Secret.")
        exit(1)

    print("Token received successfully.\n")

except requests.exceptions.HTTPError as e:
    print(f"ERROR: Could not get OAuth token: {e}")
    exit(1)


# --- STEP 4: Ask the user for an incident number ---
print("=== ServiceNow Incident Fetcher ===")
incident_number = input("Enter incident number (e.g. INC0010034): ").strip().upper()

if not incident_number:
    print("No incident number entered. Exiting.")
    exit(1)


# --- STEP 5: Build the API request ---
url = f"{SNOW_INSTANCE}/api/now/table/incident"

params = {
    "sysparm_query":  f"number={incident_number}",
    "sysparm_fields": "number,short_description,description,priority,category,state,opened_at,assigned_to",
    "sysparm_limit":  "1"
}

# Instead of auth=(user, pass), we now send the token in the request header.
# "Bearer" is the standard word that tells the server "here is my token".
headers = {
    "Authorization": f"Bearer {access_token}"
}


# --- STEP 6: Make the API call ---
print(f"\nFetching {incident_number} from ServiceNow...\n")

try:
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    # --- STEP 7: Parse the response ---
    data = response.json()
    results = data.get("result", [])

    if not results:
        print(f"No incident found with number: {incident_number}")
        exit(1)

    incident = results[0]

    # --- STEP 8: Display the incident details ---
    print("=" * 40)
    print("INCIDENT DETAILS")
    print("=" * 40)
    print(f"Number      : {incident.get('number',            'N/A')}")
    print(f"Description : {incident.get('short_description', 'N/A')}")
    print(f"Priority    : {incident.get('priority',          'N/A')}")
    print(f"Category    : {incident.get('category',          'N/A')}")
    print(f"State       : {incident.get('state',             'N/A')}")
    print(f"Opened At   : {incident.get('opened_at',         'N/A')}")
    print(f"Assigned To : {incident.get('assigned_to',       'N/A')}")
    print("=" * 40)

    print("\nRaw JSON response:")
    print(json.dumps(incident, indent=2))


# --- STEP 9: Handle errors ---
except requests.exceptions.ConnectionError:
    print("ERROR: Could not connect to ServiceNow. Check your SNOW_INSTANCE URL.")

except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e}")

except Exception as e:
    print(f"Unexpected error: {e}")
