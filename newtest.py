# -*- coding: utf-8 -*-
"""
Created on Tue Aug 13 11:24:38 2024

@author: frixo
"""

import streamlit as st
import requests
import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time

# Set up your SQLite database
def create_database():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vpd_data
                 (timestamp TEXT, temperature REAL, humidity REAL, vpd REAL)''')
    conn.commit()
    conn.close()

# Fetch data from Met Office
def fetch_data():
    API_KEY = 'c60bd66f-905f-48d0-885b-b5aa75c436cc'
    LOCATION_ID = '3672'  # Northolt, Greater London
    BASE_URL = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{LOCATION_ID}?res=hourly&key={API_KEY}"
    response = requests.get(BASE_URL)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        st.error(f"Failed to retrieve data: {response.status_code}")
        return None

def process_data(data):
    temp = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['T'])
    humidity = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['H'])
    return temp, humidity

def calculate_vpd(temp, humidity):
    esat = 610.7 * 10 ** (7.5 * temp / (237.3 + temp))
    vpd = esat * (1 - humidity / 100)
    return vpd

def store_data(temp, humidity, vpd):
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO vpd_data VALUES (?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), temp, humidity, vpd))
    conn.commit()
    conn.close()

def get_data_past_day():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    one_day_ago = datetime.now() - timedelta(days=1)
    c.execute("SELECT timestamp, temperature, humidity, vpd FROM vpd_data WHERE timestamp >= ?", (one_day_ago.strftime("%Y-%m-%d %H:%M:%S"),))
    rows = c.fetchall()
    conn.close()
    return rows

def main():
    st.title("Vapour Pressure Deficit (VPD) Monitoring")

    create_database()

    # Container for live updates
    live_update = st.empty()

    while True:
        with live_update.container():
            data = fetch_data()
            if data:
                temp, humidity = process_data(data)
                vpd = calculate_vpd(temp, humidity)
                store_data(temp, humidity, vpd)

            # Get data from the last day
            last_day_data = get_data_past_day()
            if last_day_data:
                timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in last_day_data]
                vpd_values = [row[3] for row in last_day_data]

                # Plot the VPD
                plt.figure(figsize=(10, 5))
                plt.plot(timestamps, vpd_values, marker='o', linestyle='-', color='blue')
                plt.xlabel("Time")
                plt.ylabel("VPD (Pa)")
                plt.title("VPD Over the Past Day")
                plt.grid(True)
                st.pyplot(plt)

        # Sleep for 60 seconds before refreshing
        time.sleep(60)

if __name__ == "__main__":
    main()
