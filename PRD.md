# Product Requirement Document (PRD): Smart E-commerce Image Processor

## 1. Introduction
### 1.1 Purpose
To provide a user-friendly graphical interface for the existing automated image processing workflow. The tool automates resizing, padding, and slicing of e-commerce product images, ensuring they meet platform requirements (e.g., square main images, sliced detail images) without manual editing.

### 1.2 Target Audience
- E-commerce operators
- Designers managing large volumes of product images

## 2. Product Scope
The product consists of a **Local Web-based Dashboard** that interacts with a **Local Python Backend**.
- **Frontend**: React-based UI for configuration, monitoring, and operation.
- **Backend**: FastAPI wrapper around the existing `process_images.py` logic to handle file system operations efficiently.

## 3. Key Features

### 3.1 Workspace Management
- **Directory Selection**: User inputs or selects the root directory containing product subfolders (e.g., `31021_主图`).
- **Structure Analysis**: Automatically scan and categorize folders into "Main Images" (主图) and "Detail Images" (商详图).
- **Statistics**: Display total products, image counts, and estimated processing time.

### 3.2 Configuration (Advanced Settings)
- **Main Image Rules**:
  - Target Resolution Range (Default: 800x800 - 1800x1800).
  - Canvas Filling: Auto-center with White background.
- **Detail Image Rules**:
  - Width Constraint: 800px - 1800px.
  - Slicing Threshold: Height > 10000px (Auto-slice).
- **Output Settings**:
  - Max File Size (Default: 5MB).
  - Quality Compression (Auto-adjust to fit size limit).
  - Output Directory naming convention.

### 3.3 Processing & Monitoring
- **Real-time Progress**: Visual progress bar.
- **Live Logs**: Terminal-like display showing current file being processed.
- **Error Handling**: Skip corrupted files and report errors without stopping the queue.

### 3.4 Post-Processing
- **Open Output Folder**: One-click access to the processed images.
- **Comparison Preview**: (Nice to have) Side-by-side view of Original vs Processed for a sample image.

## 4. Technical Architecture
- **Frontend**: React + Vite + Tailwind CSS + Lucide React (Icons).
- **Backend**: Python FastAPI (serving the frontend and exposing processing API).
- **Communication**: REST API / WebSocket (for real-time logs).

## 5. UI/UX Design Guidelines
- **Theme**: Clean, Professional (Light/Dark mode support).
- **Feedback**: Clear success/error indicators.
- **Efficiency**: "One-Click Run" for standard workflows.
