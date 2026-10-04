from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.schemas.job import JobCreate, JobResponse


def _resolve_id(job_id: str) -> ObjectId:
    """Convert a string ID to ObjectId; raise 400 on bad format."""
    try:
        return ObjectId(job_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID format.",
        )


def _fmt_job(doc: dict) -> dict:
    """Stringify _id before returning to the caller."""
    doc["_id"] = str(doc["_id"])
    return doc


class JobService:

    # ── CREATE ────────────────────────────────────────────────────────────────

    @staticmethod
    def create_job(db: Database, payload: JobCreate) -> dict:
        """Insert a new job listing."""
        now = datetime.now(timezone.utc)
        job_doc: Dict[str, Any] = {
            **payload.model_dump(exclude_none=False),
            "skills": [],
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = db["jobs"].insert_one(job_doc)
            if not result.acknowledged or not result.inserted_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create job record.",
                )
            job_doc["_id"] = str(result.inserted_id)
            return job_doc
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while creating job.",
            )

    # ── READ (single) ─────────────────────────────────────────────────────────

    @staticmethod
    def get_job(db: Database, job_id: str) -> dict:
        """Fetch a single job by its MongoDB ObjectId string."""
        obj_id = _resolve_id(job_id)
        doc = db["jobs"].find_one({"_id": obj_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found.",
            )
        return _fmt_job(doc)

    # ── READ (list / search) ──────────────────────────────────────────────────

    @staticmethod
    def list_jobs(
        db: Database,
        title: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
        skill: Optional[str] = None,
        experience_min: Optional[int] = None,
        experience_max: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """
        Return a paginated, optionally filtered list of jobs.
        Text filters are case-insensitive regex matches.
        """
        query: Dict[str, Any] = {}

        if title:
            query["title"] = {"$regex": title, "$options": "i"}
        if company:
            query["company"] = {"$regex": company, "$options": "i"}
        if location:
            query["location"] = {"$regex": location, "$options": "i"}
        if source:
            query["source"] = {"$regex": source, "$options": "i"}
        if skill:
            query["skills"] = {"$in": [skill]}
        if experience_min is not None:
            query.setdefault("experience_min", {})
            query["experience_min"]["$gte"] = experience_min
        if experience_max is not None:
            query.setdefault("experience_max", {})
            query["experience_max"]["$lte"] = experience_max

        cursor = (
            db["jobs"]
            .find(query)
            .sort("created_at", -1)   # newest first
            .skip(skip)
            .limit(limit)
        )
        return [_fmt_job(doc) for doc in cursor]

    # ── UPDATE (partial patch) ────────────────────────────────────────────────

    @staticmethod
    def update_job(db: Database, job_id: str, payload: dict) -> dict:
        """
        Partial update – only the fields present in `payload` (non-None) are changed.
        Caller must pass a plain dict of fields to update.
        """
        obj_id = _resolve_id(job_id)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update fields provided.",
            )

        payload["updated_at"] = datetime.now(timezone.utc)

        try:
            result = db["jobs"].find_one_and_update(
                {"_id": obj_id},
                {"$set": payload},
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while updating job.",
            )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found.",
            )
        return _fmt_job(result)

    # ── DELETE ────────────────────────────────────────────────────────────────

    @staticmethod
    def delete_job(db: Database, job_id: str) -> dict:
        """Permanently remove a job listing."""
        obj_id = _resolve_id(job_id)
        try:
            result = db["jobs"].delete_one({"_id": obj_id})
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while deleting job.",
            )
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found.",
            )
        return {"detail": "Job deleted successfully.", "job_id": job_id}

    # ── ADD / REMOVE skills (convenience helpers) ─────────────────────────────

    @staticmethod
    def add_skills(db: Database, job_id: str, skills: List[str]) -> dict:
        """Add one or more skill tags to a job (no duplicates via $addToSet)."""
        obj_id = _resolve_id(job_id)
        try:
            result = db["jobs"].find_one_and_update(
                {"_id": obj_id},
                {
                    "$addToSet": {"skills": {"$each": skills}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while adding skills.",
            )
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        return _fmt_job(result)

    @staticmethod
    def remove_skills(db: Database, job_id: str, skills: List[str]) -> dict:
        """Remove specific skill tags from a job."""
        obj_id = _resolve_id(job_id)
        try:
            result = db["jobs"].find_one_and_update(
                {"_id": obj_id},
                {
                    "$pull": {"skills": {"$in": skills}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while removing skills.",
            )
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        return _fmt_job(result)
