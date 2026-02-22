🚗 RideSync — Smart Ride Sharing Platform

RideSync is a real-time ride sharing web application built using Python, Streamlit, and SQLite that connects passengers and drivers for solo or shared rides within a defined location network.

The platform supports:

Passenger ride booking

Driver ride acceptance

Shared ride matching

Live request management

Ride history tracking

Route visualization on map

The system simulates a mini ride-hailing ecosystem similar to Uber/Ola for educational and prototype purposes.

🚀 Features

✅ User Authentication (Login / Signup)
✅ Passenger & Driver Modes
✅ Solo and Shared Ride Booking
✅ Real-Time Ride Requests via SQLite
✅ Smart Ride Matching for Shared Trips
✅ Interactive Route Map using Folium
✅ Distance & Price Calculation
✅ Driver Earnings Tracking
✅ Ride History with Statistics
✅ Download Ride History (CSV)
✅ Auto Cleanup of Expired Requests
✅ Responsive Streamlit Dashboard

🧠 How It Works

The application uses:

Streamlit session state for UI state management

SQLite database (ridesync.db) for persistent storage

OSRM API for route distance calculation

Folium maps for visualization

Custom pricing algorithm based on distance and vehicle type

The database contains three main tables:

users → login credentials

rides → completed ride history

active_requests → live ride booking system

The system automatically removes expired ride requests and prevents duplicate bookings.

📂 Project Structure
RideSync/
│── Ridesync.py        # Main Streamlit application
│── ridesync.db        # SQLite database
│── README.md          # Project documentation

🛠️ Technologies Used

Python 3

Streamlit

SQLite3

Pandas

Folium

OSRM Routing API

Polyline

Requests

🔐 Demo Login

You can use dummy accounts included in the system:

Username: d1
Password: 123

Username: p1
Password: 123

📍 Supported Locations

The system currently supports predefined locations such as:

LJU Campus

Prahlad Nagar

Satellite

Vastrapur

Bodakdev

Navrangpura

Ambawadi

These can be expanded easily in the code.
