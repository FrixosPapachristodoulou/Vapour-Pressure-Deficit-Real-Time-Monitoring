import requests
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from matplotlib import rcParams
import time
import matplotlib.gridspec as gridspec
from  matplotlib.widgets import Button

current_plot = "dialy"

# API details
API_KEY = 'c60bd66f-905f-48d0-885b-b5aa75c436cc'  # Your actual API key
LOCATION_ID = '3672'  # Location ID for Northolt, Greater London
BASE_URL = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{LOCATION_ID}?res=hourly&key={API_KEY}"

# Set modern fonts and other style configurations
#rcParams['font.family'] = 'sans-serif'
#rcParams['font.family'] = 'Gill Sans Nova'  # Modern sans-serif font
rcParams['text.color'] = 'white'
rcParams['axes.labelcolor'] = 'white'
rcParams['xtick.color'] = 'white'
rcParams['ytick.color'] = 'white'
rcParams['axes.facecolor'] = 'black'
rcParams['figure.facecolor'] = 'black'
rcParams['axes.edgecolor'] = 'white'  # Set axis lines to white

def create_database():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vpd_data
                 (timestamp TEXT, temperature REAL, humidity REAL, vpd REAL)''')
    conn.commit()
    conn.close()

def fetch_data():
    response = requests.get(BASE_URL)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return None

def process_data(data):
    # Extract temperature and humidity from the JSON response
    temp = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['T'])
    humidity = float(data['SiteRep']['DV']['Location']['Period'][0]['Rep'][0]['H'])
    return temp, humidity

def calculate_vpd(temp, humidity):
    # Calculate saturation vapour pressure (esat) in Pa
    esat = 610.7 * 10 ** (7.5 * temp / (237.3 + temp))
    # Calculate VPD in Pa
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


def get_last_10_vpd():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    c.execute("SELECT vpd FROM vpd_data ORDER BY timestamp DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_last_10_days_vpd():
    conn = sqlite3.connect('weather_data.db')
    c = conn.cursor()
    ten_days_ago = datetime.now() - timedelta(days=10)
    c.execute("SELECT timestamp, AVG(vpd) FROM vpd_data WHERE timestamp >= ? GROUP BY DATE(timestamp)", (ten_days_ago.strftime("%Y-%m-%d %H:%M:%S"),))
    rows = c.fetchall()
    conn.close()
    return rows

def plot_daily_vpd(ax, ax_text):
    data = get_data_past_day()
    last_10_vpd = get_last_10_vpd()

    if data:
        timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in data]
        vpd_values = [row[3] for row in data]
        temps = [row[1] for row in data]
        humidities = [row[2] for row in data]

        # Adjust figsize to make the plot wider
        #fig = plt.figure(figsize=(12, 8))  # Increased width from 10 to 12 inches
        #gs = gridspec.GridSpec(2,1, height_ratios=[3,1])

        #ax = fig.add_subplot(gs[0])
        ax.clear()
        ax.plot(timestamps, vpd_values, marker='o', linestyle='-', color='white')

        last_color = 'red' if vpd_values[-1] > 706 else 'green'
        ax.plot(timestamps[-1], vpd_values[-1], marker='o', markersize=10, color=last_color)


        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.set_title("VPD Over the Past Day", color='white')
        ax.set_xlabel("Time")
        ax.set_ylabel("VPD (Pa)")
        ax.grid(True, color='gray')
        plt.xticks(rotation=0)  # Set rotation to 0 for horizontal axis numbers

        


        # Remove previous annotations
        #for ann in plt.gca().texts:
        #    ann.remove()

        # Annotate the last point with a transparent white box and an arrow
        ax.annotate(
            f'Time: {timestamps[-1].strftime("%H:%M")}\nTemp: {temps[-1]:.2f}°C\nHumidity: {humidities[-1]:.2f}%\nVPD: {vpd_values[-1]:.2f} Pa',
            (timestamps[-1], vpd_values[-1]),
            textcoords="offset points",
            xytext=(0, 20),  # Position the annotation 20 points above the data point
            ha='center',
            fontsize=15,  # Larger font size for visibility
            color=last_color,  # Match the color of the annotation with the last point
            bbox=dict(boxstyle="round,pad=0.3", edgecolor='none', facecolor='white', alpha=0.7),  # Transparent white box
            
        )
        
        if last_10_vpd:
            avg_vpd = sum(last_10_vpd) / len(last_10_vpd)
            ax.text(0.5, 1.05, f"Average VPD of Last 10 Fetchings: {avg_vpd:.2f} Pa", ha="center", fontsize=18, color="white", transform=ax.transAxes) 
        
        ax_text.clear()
        ax_text.axis('off')

        if sum(1 for v in vpd_values[-10:] if v > 706) >= 10:
            ax_text.text(0.5, 1.1, "Firewave Predicted!", ha="center", fontsize=18, color="red", weight="bold", bbox=dict(facecolor='white', alpha=0.7))

        #button_ax = fig.add_axes([0.85, 0.05,0.1,0.075])
        #button = Button(button_ax, 'Toggle Plot')
        #button.on_clicked(toggle_plot)

        #plt.ahow()

def plot_10_day_vpd(ax, ax_text):
        data = get_last_10_days_vpd()
          
        if data:
            dates = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").date() for row in data]
            avg_vpd_value = [row[1] for row in data]

            #fig = plt.figure(figsize=(12,8))
            #ax = fig.add_subplot(111)
            ax.clear()
            ax.plot(dates, avg_vpd_values, marker='o', linestyle='-', color='white')
      
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'))
            ax.set_title("Average VPD Over the Last 10 days", color='white', pad=20)
            ax.set_xlabel("Date")
            ax.set_ylabel("Average VPD (Pa)")
            ax.grid(True, color='gray')
            plt.xticks(rotation=45)

            ax_text.clear()
            ax_text.axis('off')

            #button_ax = fig.add_axes([0.85, 0.05, 0.1, 0.075])
            #button = Button(button_ax, 'Toggle Plot')
            #button.on_clicked(toggle_plot)
           
            #plt.show()

def toggle_plot(event):
        global current_plot
        if current_plot == "daily":
            plt_10_day_vpd(ax,ax_tet)
            current_plot = "10-day"
        else:
            plot_daily_vpd(ax,ax_text)
            current_plot = "daily"
        plt.draw()


fig = plt.figure(figsize=(12,8))
gs = gridspec.GridSpec(2,1, height_ratios=[3,1])

ax = fig.add_subplot(gs[0])
ax_text = fig.add_subplot(gs[1])
ax_text.axis('off')

button_ax = fig.add_axes([0.85, 0.05, 0.1, 0.075])
button = Button(button_ax, 'Toggle Plot')
button.on_clicked(toggle_plot)

plot_daily_vpd(ax, ax_text)

plt.show()


#def main():
#    create_database()
#    while True:
#        data = fetch_data()
#        if data:
#            temp, humidity = process_data(data)
#            vpd = calculate_vpd(temp, humidity)
#            store_data(temp, humidity, vpd)
#        plot_daily_vpd()
#        time.sleep(60)  # Refresh every 60 seconds
#
#if __name__ == "__main__":
#    main()




































































































