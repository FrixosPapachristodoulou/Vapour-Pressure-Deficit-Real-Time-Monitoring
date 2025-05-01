# -*- coding: utf-8 -*-
"""
Created on Mon Aug 12 18:41:14 2024

@author: frixo
"""

import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np

# Global variable to track which plot is currently displayed
current_plot = "sine"

def plot_sine_wave(ax):
    x = np.linspace(0, 2 * np.pi, 100)
    y = np.sin(x)
    ax.clear()
    ax.plot(x, y, label="Sine Wave")
    ax.set_title("Sine Wave")
    ax.legend()

def plot_cosine_wave(ax):
    x = np.linspace(0, 2 * np.pi, 100)
    y = np.cos(x)
    ax.clear()
    ax.plot(x, y, label="Cosine Wave")
    ax.set_title("Cosine Wave")
    ax.legend()

def toggle_plot(event):
    global current_plot
    if current_plot == "sine":
        plot_cosine_wave(ax)
        current_plot = "cosine"
    else:
        plot_sine_wave(ax)
        current_plot = "sine"
    plt.draw()

# Main setup
fig, ax = plt.subplots(figsize=(8, 6))

# Add a button
button_ax = plt.axes([0.8, 0.05, 0.1, 0.075])
button = Button(button_ax, 'Toggle Plot')
button.on_clicked(toggle_plot)

# Plot the initial sine wave
plot_sine_wave(ax)

plt.show()