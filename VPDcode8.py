# -*- coding: utf-8 -*-
"""
Created on Tue Aug 13 16:44:05 2024

@author: frixo
"""

import streamlit as st
import requests
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import time


st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Roboto', sans-serif;
    }
    </style>
    """, unsafe_allow_html=True)

    
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
    
    # Ensure all return statements provide three values
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')  # Format without seconds
    
    if response.status_code == 200:
        data = response.json()
        return data, f"Data fetched successfully at {timestamp}", True
    else:
        return None, f"Unsuccessful Data Fetching at {timestamp}", False

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

def plot_threshold(ax):
    # Draw a red dotted line at the 706 Pa threshold
    ax.axhline(y=706, color='red', linestyle='--', linewidth=1.5)

def plot_colored_lines(ax, timestamps, vpd_values):
    for i in range(len(vpd_values) - 1):
        x = [timestamps[i], timestamps[i + 1]]
        y = [vpd_values[i], vpd_values[i + 1]]

        if y[0] <= 706 and y[1] <= 706:
            ax.plot(x, y, color='green')
        elif y[0] > 706 and y[1] > 706:
            ax.plot(x, y, color='red')
        else:
            # If the line crosses the threshold, we split it
            slope = (y[1] - y[0]) / (x[1].timestamp() - x[0].timestamp())
            intercept = y[0] - slope * x[0].timestamp()
            crossing_x = (706 - intercept) / slope
            crossing_time = datetime.fromtimestamp(crossing_x)

            # Plot the segment below the threshold
            if y[0] < 706:
                ax.plot([x[0], crossing_time], [y[0], 706], color='green')
                ax.plot([crossing_time, x[1]], [706, y[1]], color='red')
            else:
                ax.plot([x[0], crossing_time], [y[0], 706], color='red')
                ax.plot([crossing_time, x[1]], [706, y[1]], color='green')

def get_last_10_days_vpd():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    ten_days_ago = datetime.now() - timedelta(days=10)
    yesterday = datetime.now() - timedelta(days=1)
    c.execute("SELECT date(timestamp), AVG(vpd) FROM vpd_data WHERE date(timestamp) BETWEEN ? AND ? GROUP BY date(timestamp)", 
              (ten_days_ago.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d')))
    rows = c.fetchall()
    conn.close()
    
    # Create a dictionary with all 10 days, defaulting to None
    last_10_days = { (yesterday - timedelta(days=i)).strftime('%Y-%m-%d'): None for i in range(10) }
    
    # Fill in the dictionary with actual data
    for day, avg_vpd in rows:
        last_10_days[day] = avg_vpd
    
    return last_10_days

def count_consecutive_days_above_threshold(vpd_data, threshold=706):
    consecutive_count = 0
    for avg_vpd in vpd_data.values():
        if avg_vpd is not None and avg_vpd > threshold:
            consecutive_count += 1
        else:
            break  # Stop counting if a day is found below the threshold
    return consecutive_count

def check_stored_data():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM vpd_data ORDER BY timestamp DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    print("Last 10 entries in the database:", rows)

check_stored_data()



def main():
    st.markdown(
        "<h2 style='text-align: center; font-size: 24px; margin-bottom: -25px;'>Vapour Pressure Deficit (VPD) Monitoring</h2>", 
        unsafe_allow_html=True
    )
    
    create_database()
    live_update = st.empty()

    while True:
        with live_update.container():
            try:
                data, status_message, success = fetch_data()
            except ValueError:
                data, status_message, success = None, "Error fetching data", False

            # Count consecutive days with average VPD > 706 Pa
            last_10_days_vpd = get_last_10_days_vpd()
            consecutive_days_above_threshold = count_consecutive_days_above_threshold(last_10_days_vpd)
            
            # Display a firewave prediction box below the main title
            if consecutive_days_above_threshold >= 10:
                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid darkred; 
                        border-radius: 5px; 
                        padding: 2px 10px; 
                        background-color: rgba(255, 0, 0, 0.1); 
                        color: darkred; 
                        font-weight: bold;
                        text-align: center;
                        margin-top: 2px;
                        margin-bottom: 10px">
                        Firewave Predicted - Consecutive days with VPD > 706 Pa: {consecutive_days_above_threshold}/10
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid darkgreen; 
                        border-radius: 5px; 
                        padding: 2px 10px; 
                        background-color: rgba(0, 128, 0, 0.1); 
                        color: darkgreen; 
                        font-weight: bold;
                        text-align: center;
                        margin-top: 2px;
                        margin-bottom: 10px">
                        No Firewave Predicted - Consecutive days with VPD > 706 Pa: {consecutive_days_above_threshold}/10
                    </div>
                    """, 
                    unsafe_allow_html=True
                )

            # Create two columns: one for the graph and one for the list
            col1, col2 = st.columns([2, 1])  # 2:1 ratio for width

            with col1:
                last_day_data = get_data_past_day()
                print(f"Last day data: {last_day_data}")
                
                if last_day_data:
                    timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in last_day_data]
                    vpd_values = [row[3] for row in last_day_data]
            
                    print(f"Timestamps: {timestamps}")
                    print(f"VPD Values: {vpd_values}")
            
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.clear()  # Clear the previous plot
                    ax.set_ylim(0, 2500)  # Set y-axis from 0 to 2000 Pa
            
                    plot_colored_lines(ax, timestamps, vpd_values)
                    plot_threshold(ax)  # Add the threshold line
            
                    ax.set_xlim([datetime.now() - timedelta(days=1), datetime.now()])
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n(%d/%m)'))
            
                    ax.set_xlabel("Time")
                    ax.set_ylabel("VPD (Pa)")
                    ax.set_title("VPD Over the Past Day", fontsize=14)
                    ax.grid(True)
                    plt.xticks(rotation=0)  # No rotation needed due to newline format
            
                    st.pyplot(fig)
                    plt.close(fig)  # Close the figure after rendering
                

            with col2:
                # Display the list of average daily VPD for the last 10 days
                st.markdown("<h3 style='text-align: center; font-size: 20px;margin-bottom: -20px;'>Average Daily VPD </h3>", unsafe_allow_html=True)

                for day, avg_vpd in last_10_days_vpd.items():
                    if avg_vpd is not None:
                        color = 'green' if avg_vpd < 706 else 'red'
                        st.markdown(
                            f"""
                            <div style="
                                color: {color}; 
                                font-weight: bold;">
                                {day}: {avg_vpd:.2f} Pa
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"""
                            <div style="
                                color: gray; 
                                font-weight: bold;">
                                {day}: No data fetched
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )

            # Move the success/error message to the bottom, spanning the full page width
            st.markdown(
                f"""
                <div style="
                    border: 1px solid {'darkgreen' if success else 'darkred'}; 
                    border-radius: 5px; 
                    padding: 2px 10px; 
                    background-color: {'rgba(0, 128, 0, 0.1)' if success else 'rgba(255, 0, 0, 0.1)'}; 
                    color: {'darkgreen' if success else 'darkred'}; 
                    font-weight: bold;
                    text-align: center;
                    margin-top: -8px;">
                    {status_message}
                </div>
                """, 
                unsafe_allow_html=True
            )
        
        time.sleep(60)  # Refresh every 60 seconds

if __name__ == "__main__":
    main()
