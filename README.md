# File Analytics Dashboard

A full-stack file analytics system built with **Django**, **MongoDB (analytics storage)**, **MySQL (core metadata storage)**, and a modern interactive UI. This dashboard scans a shared folder, tracks file usage, manages uploads, visualizes analytics, and provides a complete in-browser file editor.

## Features

### Core Functionalities
- Dynamic scanning of a shared folder on the server
- Tracks **file metadata**, access counts, modifications, and sizes
- File upload, replace, delete with permissions
- In-browser file viewer and editor (for editable formats)
- Hot files panel based on access frequency
- File type distribution chart (Chart.js)
- KPI metrics: total files & total storage size

### Analytics
- **MySQL** → stores real-time file metadata
- **MongoDB** → stores aggregated analytics (computed_at snapshot)
- Dashboard updates charts, hot files, and KPIs via REST API

### Teams & Roles
- User belongs to a team
- Manager-only actions: delete files, rescan shared folder
- Team members list automatically loaded from backend

### Security
- Path traversal protection on all file access
- CSRF-protected uploads and editor saves
- Role-based permissions

---

## Project Structure

```
analytics_project/
│
├── dashboard/
│   ├── views.py
│   ├── utils.py
│   ├── serializers.py
│   ├── models.py
│   ├── templates/
│   ├── static/js/dashboard.js
│   └── ...
│
├── analytics_mongo.py (MongoDB connector)
├── settings.py
└── urls.py
```

---

## Installation

### 1. Clone the repository
```
git clone https://github.com/YOUR_USERNAME/File-Analytics-Dashboard.git
cd File-Analytics-Dashboard
```

### 2. Create virtual environment
```
python -m venv venv
source venv/bin/activate    # Linux / macOS
venv\Scripts\activate       # Windows
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Configure databases

#### MySQL (metadata)
Create a DB and update:
```
DATABASES['default'] = {
    'ENGINE': 'django.db.backends.mysql',
    'NAME': 'file_analytics',
    'USER': 'root',
    'PASSWORD': '',
    'HOST': 'localhost',
    'PORT': '3306'
}
```

#### MongoDB (analytics)
Update in `settings.py`:
```python
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "file_analytics"
MONGO_COLLECTION = "analytics"
```

---

## Shared Folder Setup (Important)
This project expects a folder for storing all uploaded files.

### Default path (inside settings.py)
```python
SHARED_FOLDER_PATH = r"C:\Users\YOURNAME\File_Analytics\shared"
```

### **Anyone cloning this project MUST update** this value to match their local system.
If the folder doesn't exist, create it manually.

---

## Running the Server
```
python manage.py migrate
python manage.py runserver
```
Then open:
```
http://127.0.0.1:8000/dashboard/
```

---

## REST API Endpoints

| Method | Endpoint | Description |
|--------|-----------|-------------|
| GET | /api/analytics/ | Dashboard analytics (MongoDB-powered) |
| GET | /api/files/ | List all files |
| POST | /api/files/ | Upload new file |
| PUT | /api/files/<id>/ | Replace a file |
| DELETE | /api/files/<id>/ | Delete a file |
| POST | /api/files/<id>/access/ | Increment access count |
| POST | /api/scan_shared/ | Manager-only rescan |
| GET/POST | /api/files/<id>/content/ | In-browser file editor |
| GET | /api/user/me/ | Current user + team details |

---

## Key Design Decisions
- MySQL used for **transactional metadata** (file list, uploads, updates)
- MongoDB used for **fast analytics reads** to avoid heavy SQL aggregation
- Rescan writes fresh analytics snapshot to MongoDB
- Prevents path traversal attacks on file access
- Handles external edits using a reliable timestamp comparison

---

## Notes for Contributors
- If you clone the project, **update SHARED_FOLDER_PATH**
- Ensure MongoDB and MySQL are both running
- Use Django admin to manage users & teams

---

## Author
Developed by **Prasanna Bhujbal** 
