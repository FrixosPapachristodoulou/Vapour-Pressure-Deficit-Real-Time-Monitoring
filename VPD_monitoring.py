# -*- coding: utf-8 -*-
"""
Created on Thu Aug 15 12:00:10 2024

@author: frixo
"""

# Code for Vapour Pressure Deficit Real-Time Monitoring
# Date: 15/08/2024

import streamlit as st
import requests
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import time

# Font Styling with Streamlit
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Roboto', sans-serif;
    }

    .section-title {
    font-size: 18px;
    font-weight: bold;
    text-align: left;
    padding-bottom: 3px;  /* Space between text and line */
    margin-bottom: 0px;  /* Space below the title */
    display: flex;
    align-items: center;
    }

    .section-title:after {
    content: "";
    flex: 1;
    margin-left: 10px;
    border-bottom: 2px solid #000; /* This is the horizontal line */
    }
    </style>
    """, unsafe_allow_html=True)
    
    
    
# Set up SQLite database
def create_database():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vpd_data
                 (timestamp TEXT, temperature REAL, humidity REAL, vpd REAL)''')
    conn.commit()
    conn.close()

# Fetch data from Met Office
def fetch_data():
    API_KEY = 'c60bd66f-905f-48d0-885b-b5aa75c436cc' # Generated API Key
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
    try:
        temp = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['T'])
        humidity = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['H'])
        return temp, humidity
    except (KeyError, IndexError, TypeError) as e:
        # Log the error and return None to indicate a problem
        print(f"Error processing data: {e}")
        return None, None

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

        # Ensure timestamps are datetime objects
        if not all(isinstance(t, datetime) for t in x):
            continue

        # Ensure VPD values are floats
        if not all(isinstance(v, (float, int)) for v in y):
            continue

        try:
            # Calculate slope and intercept
            slope = (y[1] - y[0]) / (x[1].timestamp() - x[0].timestamp())
            intercept = y[0] - slope * x[0].timestamp()
            crossing_x = (706 - intercept) / slope
            crossing_time = datetime.fromtimestamp(crossing_x)

            # Plot the segment below the threshold
            if y[0] <= 706 and y[1] <= 706:
                ax.plot(x, y, color='green')
            elif y[0] > 706 and y[1] > 706:
                ax.plot(x, y, color='red')
            else:
                if y[0] < 706:
                    ax.plot([x[0], crossing_time], [y[0], 706], color='green')
                    ax.plot([crossing_time, x[1]], [706, y[1]], color='red')
                else:
                    ax.plot([x[0], crossing_time], [y[0], 706], color='red')
                    ax.plot([crossing_time, x[1]], [706, y[1]], color='green')

        except Exception as e:
            print(f"Error in plot_colored_lines: {e}")
            continue



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

def get_last_10_fetchings():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, vpd FROM vpd_data ORDER BY timestamp DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return rows

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
                data = fetch_data()
                if data:
                    try:
                        temp, humidity = process_data(data)
                        if temp is not None and humidity is not None:
                            try:
                                vpd = calculate_vpd(temp, humidity)
                                store_data(temp, humidity, vpd)
                                status_message = "Data fetched successfully (UK Weather Observation Data)"
                                success = True
                            except Exception as e:
                                st.error(f"Error calculating or storing VPD: {e}")
                                status_message = "Error calculating/storing VPD; skipping entry."
                                success = False
                        else:
                            status_message = "Data processing failed; skipping entry."
                            success = False
                    except Exception as e:
                        st.error(f"Error processing data: {e}")
                        status_message = "Data processing failed; skipping entry."
                        success = False
                else:
                    status_message = "Unsuccessful Data Fetching."
                    success = False
            except Exception as e:
                st.error(f"Error fetching data: {e}")
                status_message = "Unsuccessful Data Fetching due to an unexpected error."
                success = False

            # Count consecutive days with average VPD > 706 Pa
            try:
                last_10_days_vpd = get_last_10_days_vpd()
                consecutive_days_above_threshold = count_consecutive_days_above_threshold(last_10_days_vpd)
            except Exception as e:
                st.error(f"Error retrieving or counting VPD data: {e}")
                last_10_days_vpd = {}
                consecutive_days_above_threshold = 0

            # Display a firewave prediction box below the main title
            try:
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
                            Firewave Predicted - Consecutive Days with VPD Above 706 Pa: {consecutive_days_above_threshold}/10
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
                            No Firewave Predicted - Consecutive Days with VPD Above 706 Pa: {consecutive_days_above_threshold}/10
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
            except Exception as e:
                st.error(f"Error displaying firewave prediction: {e}")

            # Title: Today
            st.markdown("<div class='section-title'>Today</div>", unsafe_allow_html=True)

            # Create two columns: one for the graph and one for the list
            col1, col2 = st.columns([2, 1])  # 2:1 ratio for width

            with col1:
                try:
                    last_day_data = get_data_past_day()
                    if last_day_data:
                        timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in last_day_data]
                        vpd_values = [row[3] for row in last_day_data]

                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.clear()
                        ax.set_ylim(0, 2500)
                        
                        plot_colored_lines(ax, timestamps, vpd_values)
                        plot_threshold(ax)
                        
                        ax.set_xlim([datetime.now() - timedelta(days=1), datetime.now()])
                        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n(%d/%m)'))
                        ax.set_xlabel("Time", fontsize=14)
                        ax.set_ylabel("VPD (Pa)", fontsize=14)
                        ax.set_title("VPD Over the Past Day", fontsize=14)
                        ax.grid(True)
                        plt.xticks(rotation=0)

                        st.pyplot(fig)
                        plt.close(fig)
                except Exception as e:
                    st.error(f"Error plotting the graph: {e}")

            with col2:
                try:
                    # Display the latest 10 VPD fetchings with timestamps
                    st.markdown("<h3 style='text-align: center; font-size: 20px;margin-bottom: -28px;'>Last 10 Hours</h3>", unsafe_allow_html=True)

                    last_10_fetchings = get_last_10_fetchings()
                    for timestamp, vpd in last_10_fetchings:
                        color = 'green' if vpd < 706 else 'red'
                        st.markdown(
                            f"""
                            <div style="
                                color: {color}; 
                                font-weight: bold;
                                text-align: center;">
                                {datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%H:%M (%d/%m)')}: {vpd:.2f} Pa
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                except Exception as e:
                    st.error(f"Error displaying the latest 10 VPD fetchings: {e}")

            # Title: Latest 10 days
            st.markdown("<div class='section-title'>Last 10 Days</div>", unsafe_allow_html=True)

            # Create two columns: one for the second graph and one for the list
            col3, col4 = st.columns([2, 1])  # 2:1 ratio for width

            with col3:
                try:
                    if last_10_days_vpd:
                        days = list(last_10_days_vpd.keys())  # Keep order: oldest to newest
                        avg_vpds = list(last_10_days_vpd.values())
                
                        # Plotting the average VPD over the last 10 days
                        fig2, ax2 = plt.subplots(figsize=(10, 6))
                        ax2.clear()  # Clear the previous plot
                        ax2.set_ylim(0, 2000)  # Set y-axis from 0 to 2000 Pa
                
                        # Reverse the order of the data for proper plotting from 10 days ago to yesterday
                        days = list(last_10_days_vpd.keys())[::-1]
                        avg_vpds = list(last_10_days_vpd.values())[::-1]
                
                        # Add margin on both sides
                        ax2.set_xlim(-0.3, len(days) - 0.7)
                
                        # Plot the VPD data with small dots and colored lines
                        for i in range(len(days)):
                            if avg_vpds[i] is not None:
                                color = 'green' if avg_vpds[i] < 706 else 'red'
                                ax2.plot(i, avg_vpds[i], 'o', color=color)  # Small dot for each day
                                if i < len(days) - 1:  # Plot lines between points
                                    if avg_vpds[i + 1] is not None:
                                        # Determine where the line crosses the threshold
                                        if (avg_vpds[i] < 706 and avg_vpds[i + 1] > 706) or (avg_vpds[i] > 706 and avg_vpds[i + 1] < 706):
                                            slope = (avg_vpds[i + 1] - avg_vpds[i]) / (i + 1 - i)
                                            intercept = avg_vpds[i] - slope * i
                                            crossing_x = (706 - intercept) / slope
                                            ax2.plot([i, crossing_x], [avg_vpds[i], 706], color='green' if avg_vpds[i] < 706 else 'red')
                                            ax2.plot([crossing_x, i + 1], [706, avg_vpds[i + 1]], color='red' if avg_vpds[i + 1] > 706 else 'green')
                                        else:
                                            ax2.plot([i, i + 1], [avg_vpds[i], avg_vpds[i + 1]], color=color)
                                    else:
                                        ax2.plot([i, i + 1], [avg_vpds[i], avg_vpds[i + 1]], color=color)
                
                        plot_threshold(ax2)  # Add the threshold line
                
                        # Format the days to show only day and month without the year
                        formatted_days = [datetime.strptime(day, '%Y-%m-%d').strftime('%d/%m') for day in days]
                
                        # Set x-ticks manually to match the formatted dates
                        ax2.set_xticks(range(len(days)))
                        ax2.set_xticklabels(formatted_days, rotation=0, ha='center')
                
                        # Set custom tick colors based on data availability
                        for i, day in enumerate(days):
                            if last_10_days_vpd[day] is None:
                                ax2.get_xticklabels()[i].set_color('gray')
                
                        ax2.set_xlabel("Day", fontsize=14)
                        ax2.set_ylabel("Average VPD (Pa)", fontsize=14)
                        ax2.set_title("Average Daily VPD Over the Last 10 Days", fontsize=14)
                        ax2.grid(True)
                
                        st.pyplot(fig2)
                        plt.close(fig2)  # Close the figure after rendering
                except Exception as e:
                    st.error(f"Error plotting the second graph: {e}")

            with col4:
                try:
                    st.markdown("<h3 style='text-align: center; font-size: 20px;margin-bottom: -28px;'>Average Daily VPD</h3>", unsafe_allow_html=True)

                    for day, avg_vpd in last_10_days_vpd.items():
                        if avg_vpd is not None:
                            color = 'green' if avg_vpd < 706 else 'red'
                            st.markdown(
                                f"""
                                <div style="
                                    color: {color}; 
                                    font-weight: bold;
                                    text-align: center;">
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
                                    font-weight: bold;
                                    text-align: center;">
                                    {day}: No data fetched
                                </div>
                                """, 
                                unsafe_allow_html=True
                            )
                except Exception as e:
                    st.error(f"Error displaying the Average Daily VPD list: {e}")

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
        
        time.sleep(3600)  # Refresh every 1 hour

if __name__ == "__main__":
    main()
