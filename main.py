from datetime import datetime
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    title="Team Task Management API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

tasks_db: List[Dict] = [
    {
        "id": 1,
        "title": "Thiet ke database Shop AI",
        "description": "Xay dung bang va toi uu index",
        "assignee": "QuyDev",
        "priority": 1,
        "status": "todo",
        "created_at": "2026-07-01T09:00:00Z"
    },
    {
        "id": 2,
        "title": "Code bo API Authen",
        "description": "Trien khai filter verify JWT token",
        "assignee": "FixerQ",
        "priority": 2,
        "status": "done",
        "created_at": "2026-07-01T10:00:00Z"
    }
]


class TaskCreateSchema(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=1)
    assignee: str = Field(..., min_length=1)
    priority: int = Field(..., ge=1, le=5)

    @field_validator('description', 'assignee')
    @classmethod
    def check_not_empty_or_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


class TaskStatusUpdateSchema(BaseModel):
    status: str

    @field_validator('status')
    @classmethod
    def validate_status_enum(cls, v: str) -> str:
        allowed = ["todo", "in_progress", "done"]
        if v not in allowed:
            raise ValueError(f"Invalid status. Allowed values: {allowed}")
        return v


def create_unified_envelope(status_code: int, message: str, data: any, error: Optional[str], path: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "statusCode": status_code,
            "message": message,
            "data": data,
            "error": error,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "path": path
        }
    )


def calculate_team_metrics() -> Tuple[int, int, float]:
    total_tasks = len(tasks_db)
    if total_tasks == 0:
        return 0, 0, 0.0
    completed_tasks = sum(1 for task in tasks_db if task["status"] == "done")
    completion_rate_percentage = round((completed_tasks / total_tasks) * 100.0, 2)
    return total_tasks, completed_tasks, completion_rate_percentage


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return create_unified_envelope(
        status_code=422,
        message="Lỗi: Dữ liệu đầu vào không hợp lệ hoặc sai định dạng quy định!",
        data=None,
        error="ERR-VAL-422: Validation error at Request Body fields constraint layout.",
        path=request.url.path
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "statusCode" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    
    return create_unified_envelope(
        status_code=exc.status_code,
        message="Hệ thống phát sinh lỗi cấu trúc hoặc định tuyến.",
        data=None,
        error=f"ERR-HTTP-{exc.status_code}: {str(exc.detail)}",
        path=request.url.path
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return create_unified_envelope(
        status_code=500,
        message="Lỗi hệ thống nội bộ.",
        data=None,
        error="ERR-INTERNAL-500: An unexpected runtime error occurred on the server.",
        path=request.url.path
    )


@app.get("/tasks")
async def get_all_tasks(request: Request, status: Optional[str] = None):
    if status:
        filtered_tasks = [task for task in tasks_db if task["status"] == status]
    else:
        filtered_tasks = tasks_db

    return create_unified_envelope(
        status_code=200,
        message="Lấy danh sách công việc thành công!",
        data=filtered_tasks,
        error=None,
        path=request.url.path
    )


@app.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(task_in: TaskCreateSchema, request: Request):
    for task in tasks_db:
        if task["title"] == task_in.title:
            return create_unified_envelope(
                status_code=400,
                message="Lỗi: Tiêu đề công việc này đã tồn tại trong nhóm!",
                data=None,
                error="ERR-TASK-01: Task conflict: Title field duplicates an existing record.",
                path=request.url.path
            )

    max_id = max([task["id"] for task in tasks_db]) if tasks_db else 0
    new_id = max_id + 1
    current_time = datetime.utcnow().isoformat() + "Z"

    new_task = {
        "id": new_id,
        "title": task_in.title,
        "description": task_in.description,
        "assignee": task_in.assignee,
        "priority": task_in.priority,
        "status": "todo",
        "created_at": current_time
    }
    tasks_db.append(new_task)

    return create_unified_envelope(
        status_code=201,
        message="Khởi tạo công việc mới thành công!",
        data=new_task,
        error=None,
        path=request.url.path
    )


@app.put("/tasks/{task_id}")
async def update_task_status(task_id: int, status_in: TaskStatusUpdateSchema, request: Request):
    target_task = next((task for task in tasks_db if task["id"] == task_id), None)

    if not target_task:
        return create_unified_envelope(
            status_code=404,
            message="Lỗi: Không tìm thấy ID công việc yêu cầu trong hệ thống!",
            data=None,
            error="ERR-TASK-03: Resource missing error: Target task entity parameter [task_id] cannot be located.",
            path=request.url.path
        )

    if target_task["status"] == "done":
        return create_unified_envelope(
            status_code=400,
            message="Lỗi: Công việc đã hoàn thành, không thể thay đổi trạng thái lùi lại!",
            data=None,
            error="ERR-TASK-04: Business logic error: Modification denied. Task status is already locked as 'done'.",
            path=request.url.path
        )

    target_task["status"] = status_in.status

    return create_unified_envelope(
        status_code=200,
        message="Cập nhật tiến độ công việc thành công!",
        data=target_task,
        error=None,
        path=request.url.path
    )


@app.get("/tasks/analytics/dashboard")
async def get_dashboard_analytics(request: Request):
    total_tasks, completed_tasks, completion_rate_percentage = calculate_team_metrics()
    
    analytics_data = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "completion_rate_percentage": completion_rate_percentage
    }

    return create_unified_envelope(
        status_code=200,
        message="Lấy số liệu thống kê hiệu suất nhóm thành công!",
        data=analytics_data,
        error=None,
        path=request.url.path
    )