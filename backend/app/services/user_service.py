import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.models.skill import Skill
from app.schemas.user import UserProfileCreate, UserProfileUpdate


def _fmt_user(doc: dict) -> dict:
    """Stringify _id and strip the password before returning to the caller."""
    doc["_id"] = str(doc["_id"])
    doc.pop("password", None)
    if "skills" in doc and isinstance(doc["skills"], list):
        doc["skills"] = [str(s) for s in doc["skills"]]
    else:
        doc["skills"] = []
    return doc


def _resolve_skill_ids(db: Database, skill_inputs: List[str]) -> List[ObjectId]:
    """
    Given a list of skill names or ObjectId hex strings, looks up their
    corresponding MongoDB ObjectId from the master skills collection.
    Strictly requires skills to already exist in the master catalog.
    Raises HTTPException (400) if any skill is not found.
    """
    resolved_ids: List[ObjectId] = []
    missing_skills: List[str] = []

    for item in skill_inputs:
        item_clean = item.strip()
        if not item_clean:
            continue

        skill_doc = None
        if ObjectId.is_valid(item_clean):
            skill_doc = db["skills"].find_one({"_id": ObjectId(item_clean)})

        if not skill_doc:
            skill_doc = db["skills"].find_one(
                {"name": {"$regex": f"^{re.escape(item_clean)}$", "$options": "i"}}
            )

        if skill_doc:
            if skill_doc["_id"] not in resolved_ids:
                resolved_ids.append(skill_doc["_id"])
        else:
            missing_skills.append(item_clean)

    if missing_skills:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The following skill(s) do not exist in the master catalog: "
                f"{', '.join(missing_skills)}. You can only select from existing master skills."
            ),
        )

    return resolved_ids


def _resolve_id(user_id: str) -> ObjectId:
    """Convert a string ID to ObjectId, raising 400 on bad format."""
    try:
        return ObjectId(user_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format.",
        )


class UserService:

    # ── CREATE (profile) ─────────────────────────────────────────────────────

    @staticmethod
    def create_profile(db: Database, user_id: str, payload: UserProfileCreate) -> dict:
        """
        Attach / initialise a profile on an existing auth user.
        Raises 422 if a student tries to supply current_job.
        """
        obj_id = _resolve_id(user_id)

        user_doc = db["users"].find_one({"_id": obj_id})
        if not user_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        if payload.is_student and payload.current_job is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Students cannot have a current_job. Set is_student=false to add employment details.",
            )

        update_fields: Dict[str, Any] = {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "state": payload.state,
            "city": payload.city,
            "is_student": payload.is_student,
            "current_job": payload.current_job.model_dump() if payload.current_job else None,
            "interests": payload.interests or [],
            "skills": _resolve_skill_ids(db, payload.skills) if payload.skills is not None else [],
            "updated_at": datetime.now(timezone.utc),
        }

        try:
            result = db["users"].find_one_and_update(
                {"_id": obj_id},
                {"$set": update_fields},
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while updating profile.",
            )

        return _fmt_user(result)

    # ── READ (single user) ───────────────────────────────────────────────────

    @staticmethod
    def get_user(db: Database, user_id: str) -> dict:
        obj_id = _resolve_id(user_id)
        doc = db["users"].find_one({"_id": obj_id})
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return _fmt_user(doc)

    # ── READ (list all users) ────────────────────────────────────────────────

    @staticmethod
    def list_users(
        db: Database,
        state: Optional[str] = None,
        city: Optional[str] = None,
        is_student: Optional[bool] = None,
        interest: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: Dict[str, Any] = {}
        if state:
            query["state"] = {"$regex": state, "$options": "i"}
        if city:
            query["city"] = {"$regex": city, "$options": "i"}
        if is_student is not None:
            query["is_student"] = is_student
        if interest:
            query["interests"] = {"$in": [interest]}

        cursor = db["users"].find(query).skip(skip).limit(limit)
        return [_fmt_user(doc) for doc in cursor]

    # ── UPDATE (partial patch) ────────────────────────────────────────────────

    @staticmethod
    def update_user(db: Database, user_id: str, payload: UserProfileUpdate) -> dict:
        obj_id = _resolve_id(user_id)

        # Build only the fields that were actually provided
        update_fields: Dict[str, Any] = {}

        if payload.first_name is not None:
            update_fields["first_name"] = payload.first_name
        if payload.last_name is not None:
            update_fields["last_name"] = payload.last_name
        if payload.state is not None:
            update_fields["state"] = payload.state
        if payload.city is not None:
            update_fields["city"] = payload.city

        # is_student toggle
        if payload.is_student is not None:
            update_fields["is_student"] = payload.is_student
            # When switching to student mode, clear current_job
            if payload.is_student:
                update_fields["current_job"] = None

        if payload.current_job is not None:
            # Prevent setting job while student flag is True in DB
            existing = db["users"].find_one({"_id": obj_id}, {"is_student": 1})
            effective_student = update_fields.get(
                "is_student", existing.get("is_student", False) if existing else False
            )
            if effective_student:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cannot set current_job for a student. Set is_student=false first.",
                )
            update_fields["current_job"] = payload.current_job.model_dump()

        if payload.interests is not None:
            update_fields["interests"] = payload.interests

        if payload.skills is not None:
            update_fields["skills"] = _resolve_skill_ids(db, payload.skills)

        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update fields provided.",
            )

        update_fields["updated_at"] = datetime.now(timezone.utc)

        try:
            result = db["users"].find_one_and_update(
                {"_id": obj_id},
                {"$set": update_fields},
                return_document=True,
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while updating user.",
            )

        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        return _fmt_user(result)

    # ── DELETE ────────────────────────────────────────────────────────────────

    @staticmethod
    def delete_user(db: Database, user_id: str) -> dict:
        obj_id = _resolve_id(user_id)
        try:
            result = db["users"].delete_one({"_id": obj_id})
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while deleting user.",
            )
        if result.deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return {"detail": "User deleted successfully.", "user_id": user_id}

    # ── USER SKILLS MANAGEMENT ───────────────────────────────────────────────

    @staticmethod
    def get_user_skills(db: Database, user_id: str) -> List[Skill]:
        """Fetch full skill documents attached to a user."""
        from app.services.skill_service import SkillService
        return SkillService.get_skills(db=db, user_id=user_id)

    @staticmethod
    def add_user_skills(db: Database, user_id: str, skills: List[str]) -> List[Skill]:
        """
        Add skills to a user's profile by skill names or IDs (deduplicated).
        Returns the updated list of Skill documents.
        """
        obj_id = _resolve_id(user_id)
        resolved_ids = _resolve_skill_ids(db, skills)

        if not resolved_ids:
            return UserService.get_user_skills(db, user_id)

        try:
            db["users"].update_one(
                {"_id": obj_id},
                {
                    "$addToSet": {"skills": {"$each": resolved_ids}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
            )
        except PyMongoError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error while adding user skills: {str(exc)}",
            )

        return UserService.get_user_skills(db, user_id)

    @staticmethod
    def remove_user_skills(db: Database, user_id: str, skills: List[str]) -> List[Skill]:
        """
        Remove skills from a user's profile by skill names or IDs.
        Returns the remaining list of Skill documents.
        """
        obj_id = _resolve_id(user_id)
        resolved_ids = _resolve_skill_ids(db, skills)

        if not resolved_ids:
            return UserService.get_user_skills(db, user_id)

        try:
            db["users"].update_one(
                {"_id": obj_id},
                {
                    "$pull": {"skills": {"$in": resolved_ids}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
            )
        except PyMongoError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error while removing user skills: {str(exc)}",
            )

        return UserService.get_user_skills(db, user_id)
