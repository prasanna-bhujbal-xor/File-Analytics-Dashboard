File Analytics Dashboard

A full-stack file analytics and monitoring system built with Django, MySQL, and MongoDB.

Overview
The File Analytics Dashboard is an enterprise-style web application that provides:
Real-time file metadata tracking
Hot files analytics
In-browser file editing
Team-based permissions
Automatic shared-folder scanning
MongoDB-powered analytics caching
Upload, replace, and delete operations directly from UI
It is designed for organizations that maintain a shared file directory and need visibility into file usage, changes, and team activity.

Key Features
File Management:

 Upload new files
 Replace existing files
 Delete files (Manager role only)
 In-browser editor (txt, csv, md, json, py, html, js, css, docx, etc.)
 Direct file viewing
 Safe path validation to prevent traversal attacks

Analytics Dashboard:

 Total files and total storage usage
 File type distribution chart (Chart.js)
 Hot files list
 Recent uploads
 Live access-count tracking
 MongoDB caching for optimized analytics loading

File Access Tracking
Every time a user views a file, the system automatically increments its access_count, updates the database, and refreshes analytics.

Role-Based Access
Manager can rescan shared folder, replace, delete, edit
Member can read all files
Team-specific modification permissions

Shared Folder Scanner
The backend scanner detects:
New files added externally
Modified files (based on mtime)
Deleted files
Updates metadata correctly
Marks external edits as System (external edit)

Tech Stack
Layer	Technology
Backend:	Django, Django REST Framework
Frontend:	HTML, Bootstrap 5, Vanilla JavaScript
Main Database:	MySQL (stores file metadata + user/team data)
Analytics Cache:	MongoDB
Charts:	Chart.js
File System:	OS-level scanning

Project Structure
File_Analytics/
│── analytics_project/
│   ├── dashboard/ 
│   │   ├── views.py
│   │   ├── models.py
│   │   ├── utils.py
│   │   ├── serializers.py
│   │   ├── static/dashboard/dashboard.js
│   │   └── templates/dashboard/
│   └── settings.py
│
└── shared_files/   ← MUST configure this yourself

 IMPORTANT — REQUIRED CHANGES AFTER CLONING
1️. Update the shared folder path

In settings.py, set:

SHARED_FOLDER_PATH = r"C:\Path\To\Your\SharedFolder"

2.Update MongoDB connection details
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB_NAME = "file_analytics"
MONGO_COLLECTION_NAME = "analytics_cache"

How to Run the Project
1️.Install dependencies
pip install -r requirements.txt

2️.Run migrations
python manage.py migrate

3️.Create a superuser
python manage.py createsuperuser

4️.Start the development server
python manage.py runserver
