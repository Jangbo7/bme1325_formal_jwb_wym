from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/api/v1/queues")
def list_queues(request: Request):
    queue_repo = request.app.state.container["queue_repo"]
    return {"queues": [item.model_dump() for item in queue_repo.list_views()]}
