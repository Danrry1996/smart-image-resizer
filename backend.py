import os
import shutil
import math
import asyncio
import subprocess
from typing import List, Generator
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Image Resizer API")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve Index
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration Models ---
class ProcessConfig(BaseModel):
    input_dir: str
    output_dir: str = "processed_images"
    max_size_mb: int = 5
    min_quality: int = 10
    
    # Main Image Settings
    main_min_size: int = 800
    main_max_size: int = 1800
    
    # Detail Image Settings
    detail_min_width: int = 800
    detail_max_width: int = 1800
    detail_split_height: int = 10000

class ScanResult(BaseModel):
    total_images: int
    main_images: int
    detail_images: int
    folders: List[str]

# --- Global State for Progress ---
class ProcessingState:
    def __init__(self):
        self.total = 0
        self.processed = 0
        self.current_file = ""
        self.logs: List[str] = []
        self.is_running = False
        self.errors: List[str] = []

state = ProcessingState()
connected_websockets: List[WebSocket] = []

async def notify_clients(message: dict):
    for ws in connected_websockets:
        try:
            await ws.send_json(message)
        except:
            pass # Handle disconnects gracefully in the loop

def log_message(msg: str, type="info"):
    print(msg)
    state.logs.append(msg)
    # Fire and forget notification
    asyncio.create_task(notify_clients({
        "type": "log",
        "message": msg,
        "log_type": type,
        "progress": {
            "current": state.processed,
            "total": state.total,
            "file": state.current_file
        }
    }))

# --- Core Logic (Adapted from process_images.py) ---
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def save_image(img, path, config: ProcessConfig):
    """Save image and ensure file size < MAX_SIZE_MB"""
    quality = 95
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img.save(path, 'JPEG', quality=quality)
    
    target_size_bytes = config.max_size_mb * 1024 * 1024
    
    while os.path.getsize(path) > target_size_bytes and quality > config.min_quality:
        quality -= 5
        img.save(path, 'JPEG', quality=quality)
    
    if os.path.getsize(path) > target_size_bytes:
        log_message(f"Warning: Could not compress {path} to under {config.max_size_mb}MB.", "warning")

def process_main_image(img_path, output_path, config: ProcessConfig):
    try:
        with Image.open(img_path) as img:
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha = img.convert('RGBA').split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            w, h = img.size
            max_dim = max(w, h)
            target_size = max(config.main_min_size, min(config.main_max_size, max_dim))
            
            new_img = Image.new('RGB', (target_size, target_size), (255, 255, 255))
            
            ratio = min(target_size / w, target_size / h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            paste_x = (target_size - new_w) // 2
            paste_y = (target_size - new_h) // 2
            new_img.paste(resized_img, (paste_x, paste_y))
            
            save_image(new_img, output_path, config)
            # log_message(f"Processed Main: {os.path.basename(output_path)}")
            
    except Exception as e:
        log_message(f"Error processing main image {img_path}: {e}", "error")

def process_detail_image(img_path, output_path_base, config: ProcessConfig):
    try:
        with Image.open(img_path) as img:
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha = img.convert('RGBA').split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            w, h = img.size
            
            target_w = w
            if w < config.detail_min_width:
                target_w = config.detail_min_width
            elif w > config.detail_max_width:
                target_w = config.detail_max_width
            
            if target_w != w:
                ratio = target_w / w
                target_h = int(h * ratio)
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            current_h = img.height
            if current_h > config.detail_split_height:
                num_slices = math.ceil(current_h / config.detail_split_height)
                slice_height = math.ceil(current_h / num_slices)
                
                if slice_height > config.detail_split_height:
                    slice_height = config.detail_split_height
                    num_slices = math.ceil(current_h / slice_height)

                base_name, ext = os.path.splitext(output_path_base)
                
                for i in range(num_slices):
                    top = i * slice_height
                    bottom = min((i + 1) * slice_height, current_h)
                    
                    crop_img = img.crop((0, top, img.width, bottom))
                    slice_path = f"{base_name}_{i}{ext}"
                    save_image(crop_img, slice_path, config)
                    # log_message(f"Processed Slice: {os.path.basename(slice_path)}")
            else:
                save_image(img, output_path_base, config)
                # log_message(f"Processed Detail: {os.path.basename(output_path_base)}")
                
    except Exception as e:
        log_message(f"Error processing detail image {img_path}: {e}", "error")

async def run_processing(config: ProcessConfig):
    global state
    state.is_running = True
    state.logs = []
    state.processed = 0
    state.errors = []
    
    input_dir = config.input_dir
    output_dir_base = os.path.join(input_dir, config.output_dir)
    
    ensure_dir(output_dir_base)
    
    # First pass: count files
    log_message("Scanning files...")
    files_to_process = []
    for root, dirs, files in os.walk(input_dir):
        if config.output_dir in root:
            continue
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                files_to_process.append(os.path.join(root, file))
    
    state.total = len(files_to_process)
    log_message(f"Found {state.total} images to process.")
    
    for input_path in files_to_process:
        if not state.is_running:
            break
            
        state.current_file = os.path.basename(input_path)
        
        # Calculate relative path for output
        rel_path = os.path.relpath(os.path.dirname(input_path), input_dir)
        output_dir = os.path.join(output_dir_base, rel_path)
        ensure_dir(output_dir)
        output_path = os.path.join(output_dir, os.path.basename(input_path))
        
        # Determine type
        if '主图' in input_path:
             # Skip check logic for simplicity or add it back
             process_main_image(input_path, output_path, config)
        elif '商详图' in input_path:
             process_detail_image(input_path, output_path, config)
        else:
             # Default to main image logic if unknown, or skip
             # log_message(f"Skipping unknown type folder: {input_path}", "warning")
             pass
             
        state.processed += 1
        
        # Rate limit updates to avoid flooding WS
        if state.processed % 5 == 0 or state.processed == state.total:
             await notify_clients({
                "type": "progress",
                "progress": {
                    "current": state.processed,
                    "total": state.total,
                    "file": state.current_file
                }
            })
            
        # Yield control
        await asyncio.sleep(0)

    state.is_running = False
    log_message("Processing Complete!", "success")
    await notify_clients({"type": "complete"})

# --- API Endpoints ---

@app.get("/api/scan")
def scan_directory(path: str = "."):
    """Scan directory for stats"""
    if path == ".":
        path = os.getcwd()
        
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"message": "Directory not found"})
        
    stats = {
        "total_images": 0,
        "main_images": 0,
        "detail_images": 0,
        "folders": []
    }
    
    for root, dirs, files in os.walk(path):
        if 'processed_images' in root:
            continue
            
        has_images = False
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                stats["total_images"] += 1
                has_images = True
                if '主图' in root:
                    stats["main_images"] += 1
                elif '商详图' in root:
                    stats["detail_images"] += 1
        
        if has_images:
            stats["folders"].append(os.path.relpath(root, path))
            
    return stats

@app.post("/api/process")
async def start_process(config: ProcessConfig, background_tasks: BackgroundTasks):
    if state.is_running:
        return JSONResponse(status_code=400, content={"message": "Process already running"})
    
    if config.input_dir == ".":
        config.input_dir = os.getcwd()
        
    background_tasks.add_task(run_processing, config)
    return {"message": "Processing started", "config": config}

@app.post("/api/stop")
def stop_process():
    state.is_running = False
    return {"message": "Stopping process..."}

@app.post("/api/open-folder")
def open_folder(config: ProcessConfig):
    # Ensure full path is used
    if not os.path.isabs(config.input_dir):
        config.input_dir = os.path.join(os.getcwd(), config.input_dir)
        
    path = os.path.join(config.input_dir, config.output_dir)
    
    # Ensure path exists before opening
    if not os.path.exists(path):
         ensure_dir(path)
         
    try:
        if os.name == 'nt':
            os.startfile(path)
        elif os.name == 'posix':
            subprocess.call(['open', path]) # macOS
        else:
            subprocess.call(['xdg-open', path]) # Linux
        return {"message": "Folder opened"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            # Keep alive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
