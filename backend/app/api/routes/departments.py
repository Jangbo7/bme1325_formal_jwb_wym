from fastapi import APIRouter

from app.departments.registry import list_departments


router = APIRouter()


@router.get("/api/v1/departments")
def get_departments():
    formal = list_departments(include_legacy=False)
    legacy = [item for item in list_departments(include_legacy=True) if item["id"] in {"emergency", "fever"}]
    return {
        "formal_departments": formal,
        "legacy_departments": legacy,
        "total_formal": len(formal),
    }
