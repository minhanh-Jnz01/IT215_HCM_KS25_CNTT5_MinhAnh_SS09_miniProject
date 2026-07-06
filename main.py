import re
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    title="Team Task Management API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

tasks_db: List[Dict] = []
max_current_id = 0


class TaskCreateSchema(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: str
    assignee: str = Field(..., min_length=2)
    priority: int = Field(..., ge=1, le=5)


class TaskUpdateSchema(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: str
    assignee: str = Field(..., min_length=2)
    priority: int = Field(..., ge=1, le=5)
    status: str


def create_error_envelope(status_code: int, message: str, error_code: str, tech_detail: str, path: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "statusCode": status_code,
            "message": message,
            "data": None,
            "error": f"{error_code}: {tech_detail}" if error_code else tech_detail,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "path": path
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    path = request.url.path
    errors = exc.errors()
    
    if errors:
        loc = errors[0].get("loc", [])
        type_str = errors[0].get("type", "")
        
        if "priority" in loc and ("ctx" in errors[0] and ("gt" in errors[0]["ctx"] or "lt" in errors[0]["ctx"] or "ge" in errors[0]["ctx"] or "le" in errors[0]["ctx"])):
            return create_error_envelope(
                status_code=422,
                message="Lỗi: Mức độ ưu tiên công việc không hợp lệ (Phải từ 1 đến 5)!",
                error_code="ERR-TASK-02",
                tech_detail="Validation error: Priority field numerical bounds limits constraint violation. Value must be ge=1 and le=5.",
                path=path
            )
            
        if len(loc) > 1 and loc[0] == "path" and loc[1] == "task_id" and "type_error" in type_str:
            return create_error_envelope(
                status_code=422,
                message="Lỗi: Dữ liệu đầu vào sai định dạng hoặc thiếu trường bắt buộc!",
                error_code="ERR-VAL-422",
                tech_detail="Gateway validation error: Input json parameters datatype hints mismatch or core required fields missing.",
                path=path
            )

    return create_error_envelope(
        status_code=422,
        message="Lỗi: Dữ liệu đầu vào sai định dạng hoặc thiếu trường bắt buộc!",
        error_code="ERR-VAL-422",
        tech_detail="Gateway validation error: Input json parameters datatype hints mismatch or core required fields missing.",
        path=path
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    
    return create_error_envelope(
        status_code=exc.status_code,
        message="Hệ thống phát sinh lỗi ngoại lệ.",
        error_code="",
        tech_detail=str(exc.detail),
        path=request.url.path
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return create_error_envelope(
        status_code=500,
        message="Lỗi hệ thống nội bộ.",
        error_code="ERR-INTERNAL",
        tech_detail="An unexpected error occurred on the server.",
        path=request.url.path
    )


@app.get("/tasks/search")
async def search_tasks(request: Request, keyword: Optional[str] = None, status: Optional[str] = None):
    filtered_tasks = []
    
    for task in tasks_db:
        match_keyword = True
        match_status = True
        
        if keyword:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            match_title = bool(pattern.search(task["title"]))
            match_assignee = bool(pattern.search(task["assignee"]))
            match_keyword = match_title or match_assignee
            
        if status:
            match_status = (task["status"] == status)
            
        if match_keyword and match_status:
            filtered_tasks.append({
                "id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "assignee": task["assignee"],
                "priority": task["priority"],
                "status": task["status"],
                "created_at": task["created_at"]
            })
            
    return {
        "total": len(filtered_tasks),
        "results": filtered_tasks
    }


@app.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(task_in: TaskCreateSchema, request: Request):
    global max_current_id
    path = request.url.path
    
    for task in tasks_db:
        if task["title"] == task_in.title:
            return create_error_envelope(
                status_code=400,
                message="Lỗi: Tiêu đề công việc này đã tồn tại trong nhóm!",
                error_code="ERR-TASK-01",
                tech_detail="Task conflict: Title field values duplicates an existing record in the temporary database storage.",
                path=path
            )
            
    max_current_id += 1
    current_time = datetime.utcnow().isoformat() + "Z"
    
    new_task = {
        "id": max_current_id,
        "title": task_in.title,
        "description": task_in.description,
        "assignee": task_in.assignee,
        "priority": task_in.priority,
        "status": "todo",
        "created_at": current_time,
        "internal_notes": "Internal admin log info"
    }
    
    tasks_db.append(new_task)
    
    return {
        "statusCode": 201,
        "message": "Tạo mới công việc nhóm thành công!",
        "data": {
            "id": new_task["id"],
            "title": new_task["title"],
            "description": new_task["description"],
            "assignee": new_task["assignee"],
            "priority": new_task["priority"],
            "status": new_task["status"],
            "created_at": new_task["created_at"]
        },
        "error": None,
        "timestamp": current_time,
        "path": path
    }


@app.get("/tasks/{task_id}")
async def read_task_detail(task_id: int, request: Request):
    path = request.url.path
    
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    
    if task is None:
        return create_error_envelope(
            status_code=404,
            message="Lỗi: Không tìm thấy ID công việc yêu cầu trong hệ thống!",
            error_code="ERR-TASK-04",
            tech_detail="Resource missing error: Target task entity parameter [task_id] can not be located within current active database scope.",
            path=path
        )
        
    return {
        "statusCode": 200,
        "message": "Lấy chi tiết thông tin công việc thành công!",
        "data": {
            "id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "assignee": task["assignee"],
            "priority": task["priority"],
            "status": task["status"],
            "created_at": task["created_at"]
        },
        "error": None,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "path": path
    }


@app.put("/tasks/{task_id}")
async def update_task(task_id: int, task_in: TaskUpdateSchema, request: Request):
    path = request.url.path
    
    task_index = next((index for index, t in enumerate(tasks_db) if t["id"] == task_id), None)
    
    if task_index is None:
        return create_error_envelope(
            status_code=404,
            message="Lỗi: Không tìm thấy ID công việc yêu cầu trong hệ thống!",
            error_code="ERR-TASK-04",
            tech_detail="Resource missing error: Target task entity parameter [task_id] can not be located within current active database scope.",
            path=path
        )
        
    if task_in.status not in ["todo", "in_progress", "done"]:
        return create_error_envelope(
            status_code=400,
            message="Lỗi: Trạng thái công việc cập nhật không đúng quy định!",
            error_code="ERR-TASK-03",
            tech_detail="Business logic error: Invalid task status value. Allowed enumerated selection list: ['todo', 'in_progress', 'done'].",
            path=path
        )
        
    current_task = tasks_db[task_index]
    
    current_task.update({
        "title": task_in.title,
        "description": task_in.description,
        "assignee": task_in.assignee,
        "priority": task_in.priority,
        "status": task_in.status
    })
    
    return {
        "statusCode": 200,
        "message": "Cập nhật thông tin công việc thành công!",
        "data": {
            "id": current_task["id"],
            "title": current_task["title"],
            "description": current_task["description"],
            "assignee": current_task["assignee"],
            "priority": current_task["priority"],
            "status": current_task["status"],
            "created_at": current_task["created_at"]
        },
        "error": None,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "path": path
    }


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, request: Request):
    path = request.url.path
    
    task_index = next((index for index, t in enumerate(tasks_db) if t["id"] == task_id), None)
    
    if task_index is None:
        return create_error_envelope(
            status_code=404,
            message="Lỗi: Không tìm thấy ID công việc yêu cầu trong hệ thống!",
            error_code="ERR-TASK-04",
            tech_detail="Resource missing error: Target task entity parameter [task_id] can not be located within current active database scope.",
            path=path
        )
        
    tasks_db.pop(task_index)
    
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

