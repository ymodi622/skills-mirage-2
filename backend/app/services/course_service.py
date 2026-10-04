from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.schemas.course import CourseCreate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_id(course_id: str) -> ObjectId:
    """Convert a string ID to ObjectId; raise 400 on bad format."""
    try:
        return ObjectId(course_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course ID format.",
        )


def _fmt_course(doc: dict) -> dict:
    """Stringify _id before returning to the caller."""
    doc["_id"] = str(doc["_id"])
    return doc


# ── Service ───────────────────────────────────────────────────────────────────

class CourseService:

    # ── CREATE ────────────────────────────────────────────────────────────────

    @staticmethod
    def create_course(db: Database, payload: CourseCreate) -> dict:
        """Insert a new course document."""
        now = datetime.now(timezone.utc)
        course_doc: Dict[str, Any] = {
            **payload.model_dump(exclude_none=False),
            "tags": payload.tags or [],
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = db["courses"].insert_one(course_doc)
            if not result.acknowledged or not result.inserted_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create course record.",
                )
            course_doc["_id"] = str(result.inserted_id)
            return course_doc
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while creating course.",
            )

    # ── READ (single) ─────────────────────────────────────────────────────────

    @staticmethod
    def get_course(db: Database, course_id: str) -> dict:
        """Fetch a single course by its MongoDB ObjectId string."""
        obj_id = _resolve_id(course_id)
        doc = db["courses"].find_one({"_id": obj_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found.",
            )
        return _fmt_course(doc)

    # ── READ (list / search) ──────────────────────────────────────────────────

    @staticmethod
    def list_courses(
        db: Database,
        title: Optional[str] = None,
        provider: Optional[str] = None,
        level: Optional[str] = None,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        is_free: Optional[bool] = None,
        certificate: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """
        Return a paginated, optionally filtered list of courses.
        Text filters are case-insensitive regex matches.
        """
        query: Dict[str, Any] = {}

        if title:
            query["title"] = {"$regex": title, "$options": "i"}
        if provider:
            query["provider"] = {"$regex": provider, "$options": "i"}
        if level:
            query["level"] = {"$regex": level, "$options": "i"}
        if language:
            query["language"] = {"$regex": language, "$options": "i"}
        if tag:
            query["tags"] = {"$in": [tag]}
        if is_free is not None:
            query["is_free"] = is_free
        if certificate is not None:
            query["certificate"] = certificate

        cursor = (
            db["courses"]
            .find(query)
            .sort("created_at", -1)   # newest first
            .skip(skip)
            .limit(limit)
        )
        return [_fmt_course(doc) for doc in cursor]

    # ── UPDATE (partial patch) ────────────────────────────────────────────────

    @staticmethod
    def update_course(db: Database, course_id: str, payload: dict) -> dict:
        """
        Partial update – only the fields present in `payload` are changed.
        Caller must pass a plain dict of fields to update.
        """
        obj_id = _resolve_id(course_id)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update fields provided.",
            )

        payload["updated_at"] = datetime.now(timezone.utc)

        try:
            result = db["courses"].find_one_and_update(
                {"_id": obj_id},
                {"$set": payload},
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while updating course.",
            )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found.",
            )
        return _fmt_course(result)

    # ── DELETE ────────────────────────────────────────────────────────────────

    @staticmethod
    def delete_course(db: Database, course_id: str) -> dict:
        """Permanently remove a course document."""
        obj_id = _resolve_id(course_id)
        try:
            result = db["courses"].delete_one({"_id": obj_id})
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while deleting course.",
            )
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found.",
            )
        return {"detail": "Course deleted successfully.", "course_id": course_id}

    # ── ADD / REMOVE tags ─────────────────────────────────────────────────────

    @staticmethod
    def add_tags(db: Database, course_id: str, tags: List[str]) -> dict:
        """Add one or more tags to a course (no duplicates via $addToSet)."""
        obj_id = _resolve_id(course_id)
        try:
            result = db["courses"].find_one_and_update(
                {"_id": obj_id},
                {
                    "$addToSet": {"tags": {"$each": tags}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while adding tags.",
            )
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
        return _fmt_course(result)

    @staticmethod
    def remove_tags(db: Database, course_id: str, tags: List[str]) -> dict:
        """Remove specific tags from a course."""
        obj_id = _resolve_id(course_id)
        try:
            result = db["courses"].find_one_and_update(
                {"_id": obj_id},
                {
                    "$pull": {"tags": {"$in": tags}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while removing tags.",
            )
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
        return _fmt_course(result)

    # ── SCRAPE & STORE ────────────────────────────────────────────────────────

    @staticmethod
    def scrape_and_store(
        db: Database,
        keyword: str,
        sources: Optional[List[str]] = None,
        max_results: int = 30,
    ) -> Dict[str, Any]:
        """
        Trigger the CourseScraper pipeline for *keyword*, persist results
        to the `courses` collection, and return a summary.

        Duplicates are detected by (provider, source_id) or (provider, url)
        and skipped via upsert to avoid double-inserts.
        """
        from app.scrapers.courses import CourseScraper, CourseScraperRequest

        req = CourseScraperRequest(
            keyword=keyword,
            max_results=max_results,
            sources=sources or ["nptel", "swayam", "mit_ocw", "edx", "coursera", "udemy"],
        )
        scraped: List[dict] = CourseScraper(req).run()

        inserted = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for course in scraped:
            # Build the upsert filter – prefer source_id when available
            if course.get("source_id") and course.get("provider"):
                flt = {
                    "provider": course["provider"],
                    "source_id": course["source_id"],
                }
            elif course.get("url"):
                flt = {"url": course["url"]}
            else:
                flt = {"title": course.get("title", ""), "provider": course.get("provider", "")}

            update_doc = {
                "$setOnInsert": {"created_at": now},
                "$set": {**course, "updated_at": now},
            }

            try:
                result = db["courses"].update_one(flt, update_doc, upsert=True)
                if result.upserted_id:
                    inserted += 1
                else:
                    skipped += 1
            except PyMongoError:
                skipped += 1

        return {
            "keyword": keyword,
            "scraped": len(scraped),
            "inserted": inserted,
            "skipped": skipped,
        }
